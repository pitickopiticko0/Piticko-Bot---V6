from __future__ import annotations

from datetime import timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import EMBED_COLOR, EMBED_FOOTER
from services.giveaway_service import GiveawayService
from ui.giveaway_views import GiveawayJoinView
from utils.logger import logger


class Giveaway(commands.GroupCog, name="giveaway"):
    """Kompletní systém soutěží a losování výherců."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.service = GiveawayService(bot)
        self.restore_task = None

    async def cog_load(self) -> None:
        for giveaway in self.service.get_active_giveaways():
            giveaway_id = int(giveaway["id"])
            self.bot.add_view(GiveawayJoinView(self.service, giveaway_id))

        self.restore_task = self.bot.loop.create_task(self.service.restore_active())
        logger.info("Giveaway persistentní tlačítka byla načtena.")

    async def cog_unload(self) -> None:
        self.service.cancel_all()
        if self.restore_task:
            self.restore_task.cancel()

    async def safe_defer(self, interaction: discord.Interaction) -> bool:
        try:
            await interaction.response.defer(ephemeral=True)
            return True
        except discord.NotFound:
            logger.warning("Giveaway interakce %s vypršela.", interaction.id)
            return False
        except discord.HTTPException as error:
            logger.warning("Giveaway interakci %s nešlo potvrdit: %s", interaction.id, error)
            return False

    def validate_giveaway(self, interaction: discord.Interaction, giveaway_id: int):
        giveaway = self.service.get_giveaway(giveaway_id)
        if giveaway is None:
            return None, "❌ Giveaway s tímto ID neexistuje."
        if interaction.guild is None or int(giveaway["guild_id"]) != interaction.guild.id:
            return None, "❌ Giveaway nepatří k tomuto serveru."
        return giveaway, ""

    @app_commands.command(name="create", description="Vytvoří novou giveaway.")
    @app_commands.describe(
        channel="Kanál, kam se giveaway odešle",
        prize="Cena nebo název giveaway",
        duration_minutes="Délka giveaway v minutách",
        winners="Počet výherců",
        description="Volitelný popis nebo podmínky",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def create(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        prize: str,
        duration_minutes: app_commands.Range[int, 1, 10080],
        winners: app_commands.Range[int, 1, 20] = 1,
        description: Optional[str] = None,
    ):
        if not await self.safe_defer(interaction):
            return

        if interaction.guild is None:
            await interaction.followup.send("❌ Příkaz lze použít pouze na serveru.", ephemeral=True)
            return

        bot_member = interaction.guild.me
        if bot_member is None:
            await interaction.followup.send("❌ Nepodařilo se načíst bota.", ephemeral=True)
            return

        permissions = channel.permissions_for(bot_member)
        if not (permissions.view_channel and permissions.send_messages and permissions.embed_links):
            await interaction.followup.send(
                "❌ Bot potřebuje v cílovém kanálu oprávnění Zobrazit kanál, Posílat zprávy a Vkládat odkazy.",
                ephemeral=True,
            )
            return

        end_at = self.service.now() + timedelta(minutes=duration_minutes)
        final_description = (description or "Klikni na tlačítko níže a zapoj se do soutěže.")[:1500]

        try:
            giveaway_id = self.service.create_giveaway(
                guild_id=interaction.guild.id,
                channel_id=channel.id,
                host_id=interaction.user.id,
                prize=prize[:200],
                description=final_description,
                winner_count=winners,
                end_at=end_at,
            )
            giveaway = self.service.get_giveaway(giveaway_id)
            view = GiveawayJoinView(self.service, giveaway_id)
            self.bot.add_view(view)
            message = await channel.send(
                embed=self.service.build_embed(giveaway),
                view=view,
            )
            self.service.set_message_id(giveaway_id, message.id)
            self.service.schedule(giveaway_id, end_at)
        except Exception:
            logger.exception("Vytvoření giveaway selhalo.")
            await interaction.followup.send(
                "❌ Giveaway se nepodařilo vytvořit.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"✅ Giveaway `#{giveaway_id}` byla vytvořena v {channel.mention}.",
            ephemeral=True,
        )

    @app_commands.command(name="end", description="Okamžitě ukončí aktivní giveaway.")
    @app_commands.describe(giveaway_id="ID giveaway")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def end(self, interaction: discord.Interaction, giveaway_id: int):
        if not await self.safe_defer(interaction):
            return

        giveaway, error = self.validate_giveaway(interaction, giveaway_id)
        if giveaway is None:
            await interaction.followup.send(error, ephemeral=True)
            return
        if giveaway["status"] != "active":
            await interaction.followup.send("❌ Giveaway už není aktivní.", ephemeral=True)
            return

        winners = await self.service.end_giveaway(giveaway_id)
        result = ", ".join(f"<@{user_id}>" for user_id in winners) or "žádní účastníci"
        await interaction.followup.send(
            f"✅ Giveaway byla ukončena. Výsledek: {result}",
            ephemeral=True,
        )

    @app_commands.command(name="reroll", description="Vylosuje nové výherce ukončené giveaway.")
    @app_commands.describe(giveaway_id="ID ukončené giveaway", winners="Počet nových výherců")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reroll(
        self,
        interaction: discord.Interaction,
        giveaway_id: int,
        winners: app_commands.Range[int, 1, 20] = 1,
    ):
        if not await self.safe_defer(interaction):
            return

        giveaway, error = self.validate_giveaway(interaction, giveaway_id)
        if giveaway is None:
            await interaction.followup.send(error, ephemeral=True)
            return
        if giveaway["status"] != "ended":
            await interaction.followup.send("❌ Reroll lze použít pouze u ukončené giveaway.", ephemeral=True)
            return

        winner_ids = await self.service.reroll(giveaway_id, winners)
        if not winner_ids:
            await interaction.followup.send("❌ Giveaway nemá žádné účastníky.", ephemeral=True)
            return

        mentions = ", ".join(f"<@{user_id}>" for user_id in winner_ids)
        channel = interaction.guild.get_channel(int(giveaway["channel_id"]))
        if isinstance(channel, discord.TextChannel):
            await channel.send(f"🔄 Nové losování giveaway **{giveaway['prize']}**: {mentions}")

        await interaction.followup.send(f"✅ Noví výherci: {mentions}", ephemeral=True)

    @app_commands.command(name="delete", description="Smaže zprávu giveaway a označí ji jako odstraněnou.")
    @app_commands.describe(giveaway_id="ID giveaway")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def delete(self, interaction: discord.Interaction, giveaway_id: int):
        if not await self.safe_defer(interaction):
            return

        giveaway, error = self.validate_giveaway(interaction, giveaway_id)
        if giveaway is None:
            await interaction.followup.send(error, ephemeral=True)
            return

        task = self.service.tasks.pop(giveaway_id, None)
        if task:
            task.cancel()

        channel = interaction.guild.get_channel(int(giveaway["channel_id"]))
        if isinstance(channel, discord.TextChannel) and giveaway["message_id"]:
            try:
                message = await channel.fetch_message(int(giveaway["message_id"]))
                await message.delete()
            except discord.NotFound:
                pass
            except discord.HTTPException:
                logger.exception("Giveaway zprávu %s nešlo smazat.", giveaway["message_id"])

        self.service.mark_deleted(giveaway_id)
        await interaction.followup.send(f"✅ Giveaway `#{giveaway_id}` byla odstraněna.", ephemeral=True)

    @app_commands.command(name="list", description="Zobrazí aktivní giveaway na tomto serveru.")
    async def list_giveaways(self, interaction: discord.Interaction):
        if not await self.safe_defer(interaction):
            return

        if interaction.guild is None:
            await interaction.followup.send("❌ Příkaz lze použít pouze na serveru.", ephemeral=True)
            return

        rows = self.service.get_guild_giveaways(interaction.guild.id, active_only=True)
        if not rows:
            await interaction.followup.send("📭 Na serveru není žádná aktivní giveaway.", ephemeral=True)
            return

        embed = discord.Embed(title="🎁 Aktivní giveaway", color=EMBED_COLOR)
        for row in rows[:15]:
            end_at = self.service.parse_datetime(row["end_at"])
            embed.add_field(
                name=f"#{row['id']} • {row['prize']}",
                value=(
                    f"Kanál: <#{row['channel_id']}>\n"
                    f"Výherci: **{row['winner_count']}**\n"
                    f"Účastníci: **{self.service.count_entries(int(row['id']))}**\n"
                    f"Konec: {discord.utils.format_dt(end_at, style='R')}"
                ),
                inline=False,
            )
        embed.set_footer(text=EMBED_FOOTER)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="info", description="Zobrazí detail konkrétní giveaway.")
    @app_commands.describe(giveaway_id="ID giveaway")
    async def info(self, interaction: discord.Interaction, giveaway_id: int):
        if not await self.safe_defer(interaction):
            return

        giveaway, error = self.validate_giveaway(interaction, giveaway_id)
        if giveaway is None:
            await interaction.followup.send(error, ephemeral=True)
            return

        embed = self.service.build_embed(
            giveaway,
            ended=giveaway["status"] == "ended",
        )
        embed.add_field(name="Stav", value=str(giveaway["status"]), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        original = getattr(error, "original", error)
        if isinstance(original, discord.NotFound):
            logger.warning("Giveaway interakce %s vypršela.", interaction.id)
            return

        if isinstance(error, app_commands.MissingPermissions):
            message = "❌ Tento příkaz vyžaduje oprávnění Spravovat server."
        else:
            logger.exception("Chyba giveaway příkazu: %s", error)
            message = "❌ Nastala chyba při zpracování giveaway příkazu."

        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaway(bot))
