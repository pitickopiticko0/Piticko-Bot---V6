from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from config import EMBED_COLOR, EMBED_FOOTER
from utils.database import db
from utils.logger import logger


def parse_time(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    return result if result.tzinfo else result.replace(tzinfo=timezone.utc)


class BuildModal(discord.ui.Modal, title="Odevzdat PC sestavu"):
    cpu = discord.ui.TextInput(label="Procesor", max_length=100, placeholder="Ryzen 5 7600 – 4 900 Kč")
    gpu = discord.ui.TextInput(label="Grafická karta", max_length=100, placeholder="RTX 5070 – 15 000 Kč")
    parts = discord.ui.TextInput(label="Ostatní komponenty a ceny", style=discord.TextStyle.paragraph, max_length=1000)
    price = discord.ui.TextInput(label="Celková cena v Kč", max_length=12, placeholder="30000")
    reason = discord.ui.TextInput(label="Proč je sestava dobrá?", style=discord.TextStyle.paragraph, max_length=600)

    def __init__(self, cog: "PCBuildChallenge", challenge_id: int):
        super().__init__(custom_id=f"pcbuild:modal:{challenge_id}")
        self.cog = cog
        self.challenge_id = challenge_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        challenge = db.get_pc_build_challenge(self.challenge_id)
        if challenge is None or challenge["status"] != "active":
            await interaction.response.send_message("❌ Výzva už nepřijímá sestavy.", ephemeral=True)
            return
        if datetime.now(timezone.utc) >= parse_time(challenge["end_at"]):
            await interaction.response.send_message("❌ Čas pro odevzdání vypršel.", ephemeral=True)
            return
        try:
            price = int(str(self.price).lower().replace("kč", "").replace(" ", ""))
        except ValueError:
            await interaction.response.send_message("❌ Cena musí být celé číslo.", ephemeral=True)
            return
        budget = int(challenge["budget"])
        if price <= 0 or price > budget:
            await interaction.response.send_message(
                f"❌ Sestava překračuje rozpočet **{budget:,} Kč**.".replace(",", " "), ephemeral=True,
            )
            return
        created = db.add_pc_build_entry(
            self.challenge_id, interaction.user.id, str(self.cpu), str(self.gpu),
            str(self.parts), price, str(self.reason),
        )
        message = "✅ Sestava byla uložena a při hlasování bude anonymní." if created else "❌ Sestavu už jsi odevzdal."
        if created:
            await self.cog.refresh_challenge_message(self.challenge_id)
        await interaction.response.send_message(message, ephemeral=True)


class SubmitView(discord.ui.View):
    def __init__(self, cog: "PCBuildChallenge", challenge_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.challenge_id = challenge_id
        button = discord.ui.Button(
            label="Odevzdat sestavu", emoji="🖥️", style=discord.ButtonStyle.primary,
            custom_id=f"pcbuild:submit:{challenge_id}",
        )
        button.callback = self.open_modal
        self.add_item(button)

    async def open_modal(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(BuildModal(self.cog, self.challenge_id))


class VoteView(discord.ui.View):
    def __init__(self, challenge_id: int, entry_id: int):
        super().__init__(timeout=None)
        self.challenge_id = challenge_id
        self.entry_id = entry_id
        button = discord.ui.Button(
            label="Hlasovat", emoji="🗳️", style=discord.ButtonStyle.success,
            custom_id=f"pcbuild:vote:{challenge_id}:{entry_id}",
        )
        button.callback = self.cast_vote
        self.add_item(button)

    async def cast_vote(self, interaction: discord.Interaction) -> None:
        challenge = db.get_pc_build_challenge(self.challenge_id)
        if challenge is None or challenge["status"] != "voting":
            await interaction.response.send_message("❌ Hlasování není aktivní.", ephemeral=True)
            return
        entry = next(
            (row for row in db.get_pc_build_entries(self.challenge_id) if int(row["id"]) == self.entry_id), None,
        )
        if entry is None:
            await interaction.response.send_message("❌ Sestava nebyla nalezena.", ephemeral=True)
            return
        if int(entry["user_id"]) == interaction.user.id:
            await interaction.response.send_message("❌ Pro vlastní sestavu hlasovat nemůžeš.", ephemeral=True)
            return
        db.vote_pc_build_entry(self.challenge_id, self.entry_id, interaction.user.id)
        await interaction.response.send_message("✅ Hlas byl uložen. Novým hlasem můžeš volbu změnit.", ephemeral=True)


class PCBuildChallenge(commands.GroupCog, group_name="pcvyzva"):
    """Soutěž o nejlepší PC sestavu za daný rozpočet."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.close_tasks: dict[int, asyncio.Task] = {}

    async def cog_load(self) -> None:
        for challenge in db.get_open_pc_build_challenges():
            challenge_id = int(challenge["id"])
            if challenge["status"] == "active":
                self.bot.add_view(SubmitView(self, challenge_id))
                self.schedule_close(challenge_id, parse_time(challenge["end_at"]))
            else:
                for entry in db.get_pc_build_entries(challenge_id):
                    self.bot.add_view(VoteView(challenge_id, int(entry["id"])))

    async def cog_unload(self) -> None:
        for task in self.close_tasks.values():
            task.cancel()
        self.close_tasks.clear()

    def schedule_close(self, challenge_id: int, end_at: datetime) -> None:
        old_task = self.close_tasks.pop(challenge_id, None)
        if old_task:
            old_task.cancel()
        self.close_tasks[challenge_id] = self.bot.loop.create_task(
            self.auto_close(challenge_id, end_at)
        )

    async def auto_close(self, challenge_id: int, end_at: datetime) -> None:
        try:
            delay = max(0.0, (end_at - datetime.now(timezone.utc)).total_seconds())
            await asyncio.sleep(delay)
            await self.publish_voting(challenge_id)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Automatické uzavření PC výzvy %s selhalo.", challenge_id)
        finally:
            current = self.close_tasks.get(challenge_id)
            if current is asyncio.current_task():
                self.close_tasks.pop(challenge_id, None)

    def build_challenge_embed(self, challenge, entry_count: int) -> discord.Embed:
        end_at = parse_time(challenge["end_at"])
        embed = discord.Embed(
            title="🖥️ Výzva PC stavitelů",
            description=f"Sestav nejlepší počítač pro **{challenge['purpose']}**.",
            color=EMBED_COLOR,
        )
        embed.add_field(
            name="Rozpočet",
            value=f"**{int(challenge['budget']):,} Kč**".replace(",", " "),
        )
        embed.add_field(name="Uzávěrka", value=discord.utils.format_dt(end_at, style="R"))
        embed.add_field(name="Odevzdané sestavy", value=f"**{entry_count}**")
        status_labels = {
            "active": "🟢 Příjem sestav",
            "voting": "🗳️ Hlasování",
            "ended": "🏁 Ukončeno",
            "cancelled": "❌ Zrušeno",
        }
        embed.add_field(
            name="Stav",
            value=status_labels.get(challenge["status"], str(challenge["status"])),
        )
        embed.add_field(
            name="Pravidla",
            value="Jedna sestava na hráče. Uveď všechny díly a nepřekračuj rozpočet.",
            inline=False,
        )
        embed.set_footer(text=f"Výzva #{challenge['id']} • {EMBED_FOOTER}")
        return embed

    async def refresh_challenge_message(self, challenge_id: int) -> None:
        challenge = db.get_pc_build_challenge(challenge_id)
        if challenge is None or not challenge["message_id"]:
            return
        guild = self.bot.get_guild(int(challenge["guild_id"]))
        channel = guild.get_channel(int(challenge["channel_id"])) if guild else None
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            message = await channel.fetch_message(int(challenge["message_id"]))
            count = len(db.get_pc_build_entries(challenge_id))
            view = SubmitView(self, challenge_id) if challenge["status"] == "active" else None
            await message.edit(embed=self.build_challenge_embed(challenge, count), view=view)
        except (discord.NotFound, discord.Forbidden):
            return
        except discord.HTTPException:
            logger.exception("Panel PC výzvy %s nešlo aktualizovat.", challenge_id)

    async def publish_voting(self, challenge_id: int) -> tuple[bool, str]:
        challenge = db.get_pc_build_challenge(challenge_id)
        if challenge is None:
            return False, "Výzva nebyla nalezena."
        if challenge["status"] != "active":
            return False, "Výzva už byla uzavřena."

        guild = self.bot.get_guild(int(challenge["guild_id"]))
        channel = guild.get_channel(int(challenge["channel_id"])) if guild else None
        if not isinstance(channel, discord.TextChannel):
            return False, "Kanál výzvy neexistuje nebo ho bot nevidí."

        entries = db.get_pc_build_entries(challenge_id)
        if not entries:
            db.set_pc_build_challenge_status(challenge_id, "ended")
            await self.refresh_challenge_message(challenge_id)
            await channel.send(
                f"ℹ️ PC výzva `#{challenge_id}` skončila bez odevzdaných sestav."
            )
            return True, "Výzva skončila bez odevzdaných sestav."

        await channel.send(
            f"🗳️ **Hlasování pro výzvu #{challenge_id} začíná!** "
            "Každý má jeden hlas a nesmí hlasovat pro vlastní sestavu."
        )
        for number, entry in enumerate(entries, start=1):
            embed = discord.Embed(title=f"Sestava #{number}", color=EMBED_COLOR)
            embed.add_field(name="CPU", value=entry["cpu"], inline=False)
            embed.add_field(name="GPU", value=entry["gpu"], inline=False)
            embed.add_field(name="Ostatní díly", value=entry["other_parts"][:1024], inline=False)
            embed.add_field(
                name="Cena",
                value=f"{int(entry['total_price']):,} Kč".replace(",", " "),
            )
            embed.add_field(name="Zdůvodnění", value=entry["reasoning"][:1024], inline=False)
            view = VoteView(challenge_id, int(entry["id"]))
            self.bot.add_view(view)
            await channel.send(embed=embed, view=view)

        # Stav měníme až po úspěšném zveřejnění všech sestav.
        db.set_pc_build_challenge_status(challenge_id, "voting")
        await self.refresh_challenge_message(challenge_id)
        return True, f"Zveřejněno sestav: {len(entries)}."

    @app_commands.command(name="vytvorit", description="Vytvoří soutěž o nejlepší PC sestavu.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def create(
        self, interaction: discord.Interaction, channel: discord.TextChannel,
        rozpocet: app_commands.Range[int, 5000, 500000], zamereni: str,
        delka_minut: app_commands.Range[int, 5, 10080] = 60,
    ):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Příkaz funguje pouze na serveru.", ephemeral=True)
            return
        bot_member = interaction.guild.me
        if bot_member is None:
            await interaction.response.send_message("❌ Nepodařilo se načíst oprávnění bota.", ephemeral=True)
            return
        permissions = channel.permissions_for(bot_member)
        if not (permissions.view_channel and permissions.send_messages and permissions.embed_links):
            await interaction.response.send_message("❌ Bot v kanálu nemůže posílat embedy.", ephemeral=True)
            return
        end_at = datetime.now(timezone.utc) + timedelta(minutes=delka_minut)
        challenge_id = db.create_pc_build_challenge(
            interaction.guild.id, channel.id, interaction.user.id, rozpocet,
            zamereni[:300], end_at.isoformat(),
        )
        challenge = db.get_pc_build_challenge(challenge_id)
        embed = self.build_challenge_embed(challenge, 0)
        view = SubmitView(self, challenge_id)
        self.bot.add_view(view)
        message = await channel.send(embed=embed, view=view)
        db.set_pc_build_challenge_message(challenge_id, message.id)
        self.schedule_close(challenge_id, end_at)
        await interaction.response.send_message(
            f"✅ Výzva `#{challenge_id}` byla vytvořena v {channel.mention}.", ephemeral=True,
        )

    @app_commands.command(name="uzavrit", description="Uzavře sestavy a spustí anonymní hlasování.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def close(self, interaction: discord.Interaction, id_vyzvy: int):
        await interaction.response.defer(ephemeral=True)
        challenge = db.get_pc_build_challenge(id_vyzvy)
        if challenge is None or interaction.guild is None or int(challenge["guild_id"]) != interaction.guild.id:
            await interaction.followup.send("❌ Výzva nebyla nalezena.", ephemeral=True)
            return
        if challenge["status"] != "active":
            await interaction.followup.send("❌ Výzva už byla uzavřena.", ephemeral=True)
            return
        task = self.close_tasks.pop(id_vyzvy, None)
        if task:
            task.cancel()
        success, message = await self.publish_voting(id_vyzvy)
        prefix = "✅" if success else "❌"
        await interaction.followup.send(f"{prefix} {message}", ephemeral=True)

    @app_commands.command(name="info", description="Zobrazí stav a podrobnosti PC výzvy.")
    async def info(self, interaction: discord.Interaction, id_vyzvy: int):
        challenge = db.get_pc_build_challenge(id_vyzvy)
        if challenge is None or interaction.guild is None or int(challenge["guild_id"]) != interaction.guild.id:
            await interaction.response.send_message("❌ Výzva nebyla nalezena.", ephemeral=True)
            return

        entries = db.get_pc_build_entries(id_vyzvy)
        status_labels = {
            "active": "🟢 Příjem sestav",
            "voting": "🗳️ Hlasování",
            "ended": "🏁 Ukončeno",
            "cancelled": "❌ Zrušeno",
        }
        embed = discord.Embed(
            title=f"🖥️ PC výzva #{id_vyzvy}",
            description=str(challenge["purpose"]),
            color=EMBED_COLOR,
        )
        embed.add_field(name="Stav", value=status_labels.get(challenge["status"], str(challenge["status"])))
        embed.add_field(
            name="Rozpočet",
            value=f"{int(challenge['budget']):,} Kč".replace(",", " "),
        )
        embed.add_field(name="Odevzdané sestavy", value=str(len(entries)))
        embed.add_field(
            name="Uzávěrka sestav",
            value=discord.utils.format_dt(parse_time(challenge["end_at"]), style="F"),
            inline=False,
        )
        embed.add_field(name="Kanál", value=f"<#{challenge['channel_id']}>")
        embed.add_field(name="Pořadatel", value=f"<@{challenge['host_id']}>")
        embed.set_footer(text=EMBED_FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="zrusit", description="Zruší probíhající PC výzvu.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def cancel(self, interaction: discord.Interaction, id_vyzvy: int):
        challenge = db.get_pc_build_challenge(id_vyzvy)
        if challenge is None or interaction.guild is None or int(challenge["guild_id"]) != interaction.guild.id:
            await interaction.response.send_message("❌ Výzva nebyla nalezena.", ephemeral=True)
            return
        if challenge["status"] not in ("active", "voting"):
            await interaction.response.send_message("❌ Tuto výzvu už nelze zrušit.", ephemeral=True)
            return

        task = self.close_tasks.pop(id_vyzvy, None)
        if task:
            task.cancel()
        db.set_pc_build_challenge_status(id_vyzvy, "cancelled")

        channel = interaction.guild.get_channel(int(challenge["channel_id"]))
        if isinstance(channel, discord.TextChannel):
            if challenge["message_id"]:
                try:
                    panel = await channel.fetch_message(int(challenge["message_id"]))
                    embed = panel.embeds[0] if panel.embeds else discord.Embed(title=f"PC výzva #{id_vyzvy}")
                    embed.color = discord.Color.red()
                    embed.add_field(name="Stav", value="❌ Výzva byla zrušena", inline=False)
                    await panel.edit(embed=embed, view=None)
                except (discord.NotFound, discord.Forbidden):
                    pass
                except discord.HTTPException:
                    logger.exception("Panel zrušené PC výzvy %s nešlo upravit.", id_vyzvy)
            await channel.send(f"❌ PC výzva `#{id_vyzvy}` byla zrušena správcem.")

        await interaction.response.send_message("✅ Výzva byla zrušena.", ephemeral=True)

    @app_commands.command(name="vysledky", description="Ukončí hlasování a vyhlásí výsledky.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def results(self, interaction: discord.Interaction, id_vyzvy: int):
        challenge = db.get_pc_build_challenge(id_vyzvy)
        if challenge is None or interaction.guild is None or int(challenge["guild_id"]) != interaction.guild.id:
            await interaction.response.send_message("❌ Výzva nebyla nalezena.", ephemeral=True)
            return
        if challenge["status"] != "voting":
            await interaction.response.send_message("❌ Výzva není ve hlasování.", ephemeral=True)
            return
        rows = db.get_pc_build_results(id_vyzvy)
        db.set_pc_build_challenge_status(id_vyzvy, "ended")
        await self.refresh_challenge_message(id_vyzvy)
        embed = discord.Embed(title=f"🏆 Výsledky PC výzvy #{id_vyzvy}", color=discord.Color.gold())
        for place, row in enumerate(rows[:10], start=1):
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(place, f"{place}.")
            value = f"Hlasy: **{row['votes']}** • Cena: **{int(row['total_price']):,} Kč**".replace(",", " ")
            embed.add_field(name=f"{medal} <@{row['user_id']}>", value=value, inline=False)
        embed.set_footer(text=EMBED_FOOTER)
        channel = interaction.guild.get_channel(int(challenge["channel_id"]))
        if isinstance(channel, discord.TextChannel):
            await channel.send(embed=embed)
        await interaction.response.send_message("✅ Výsledky byly zveřejněny.", ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            message = "❌ Příkaz vyžaduje oprávnění Spravovat server."
        else:
            logger.exception("Chyba PC výzvy: %s", error)
            message = "❌ Při zpracování PC výzvy nastala chyba."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PCBuildChallenge(bot))
