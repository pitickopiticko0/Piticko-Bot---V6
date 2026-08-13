from __future__ import annotations

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

    def __init__(self, challenge_id: int):
        super().__init__(custom_id=f"pcbuild:modal:{challenge_id}")
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
        await interaction.response.send_message(message, ephemeral=True)


class SubmitView(discord.ui.View):
    def __init__(self, challenge_id: int):
        super().__init__(timeout=None)
        self.challenge_id = challenge_id
        button = discord.ui.Button(
            label="Odevzdat sestavu", emoji="🖥️", style=discord.ButtonStyle.primary,
            custom_id=f"pcbuild:submit:{challenge_id}",
        )
        button.callback = self.open_modal
        self.add_item(button)

    async def open_modal(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(BuildModal(self.challenge_id))


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

    async def cog_load(self) -> None:
        for challenge in db.get_open_pc_build_challenges():
            challenge_id = int(challenge["id"])
            if challenge["status"] == "active":
                self.bot.add_view(SubmitView(challenge_id))
            else:
                for entry in db.get_pc_build_entries(challenge_id):
                    self.bot.add_view(VoteView(challenge_id, int(entry["id"])))

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
        embed = discord.Embed(
            title="🖥️ Výzva PC stavitelů",
            description=f"Sestav nejlepší počítač pro **{zamereni[:300]}**.", color=EMBED_COLOR,
        )
        embed.add_field(name="Rozpočet", value=f"**{rozpocet:,} Kč**".replace(",", " "))
        embed.add_field(name="Uzávěrka", value=discord.utils.format_dt(end_at, style="R"))
        embed.add_field(
            name="Pravidla", value="Jedna sestava na hráče. Uveď všechny díly a nepřekračuj rozpočet.", inline=False,
        )
        embed.set_footer(text=f"Výzva #{challenge_id} • {EMBED_FOOTER}")
        view = SubmitView(challenge_id)
        self.bot.add_view(view)
        message = await channel.send(embed=embed, view=view)
        db.set_pc_build_challenge_message(challenge_id, message.id)
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
        entries = db.get_pc_build_entries(id_vyzvy)
        if not entries:
            await interaction.followup.send("❌ Nebyla odevzdána žádná sestava.", ephemeral=True)
            return
        channel = interaction.guild.get_channel(int(challenge["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("❌ Kanál výzvy neexistuje.", ephemeral=True)
            return
        await channel.send(f"🗳️ **Hlasování pro výzvu #{id_vyzvy} začíná!** Každý má jeden hlas.")
        for number, entry in enumerate(entries, start=1):
            embed = discord.Embed(title=f"Sestava #{number}", color=EMBED_COLOR)
            embed.add_field(name="CPU", value=entry["cpu"], inline=False)
            embed.add_field(name="GPU", value=entry["gpu"], inline=False)
            embed.add_field(name="Ostatní díly", value=entry["other_parts"][:1024], inline=False)
            embed.add_field(name="Cena", value=f"{int(entry['total_price']):,} Kč".replace(",", " "))
            embed.add_field(name="Zdůvodnění", value=entry["reasoning"][:1024], inline=False)
            view = VoteView(id_vyzvy, int(entry["id"]))
            self.bot.add_view(view)
            await channel.send(embed=embed, view=view)
        db.set_pc_build_challenge_status(id_vyzvy, "voting")
        await interaction.followup.send(f"✅ Zveřejněno sestav: **{len(entries)}**.", ephemeral=True)

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
