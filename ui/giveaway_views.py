from __future__ import annotations

import discord

from services.giveaway_service import GiveawayService
from utils.logger import logger


class GiveawayJoinView(discord.ui.View):
    """Persistentní tlačítko pro přihlášení a odhlášení z giveaway."""

    def __init__(self, service: GiveawayService, giveaway_id: int):
        super().__init__(timeout=None)
        self.service = service
        self.giveaway_id = giveaway_id

        button = discord.ui.Button(
            label="Zúčastnit se",
            emoji="🎉",
            style=discord.ButtonStyle.success,
            custom_id=f"piticko:giveaway:join:{giveaway_id}",
        )
        button.callback = self.toggle_entry
        self.add_item(button)

    async def toggle_entry(self, interaction: discord.Interaction) -> None:
        giveaway = self.service.get_giveaway(self.giveaway_id)

        if giveaway is None or giveaway["status"] != "active":
            await interaction.response.send_message(
                "❌ Tato giveaway už není aktivní.",
                ephemeral=True,
            )
            return

        if interaction.guild is None or interaction.guild.id != int(giveaway["guild_id"]):
            await interaction.response.send_message(
                "❌ Tato giveaway nepatří k tomuto serveru.",
                ephemeral=True,
            )
            return

        if interaction.user.bot:
            await interaction.response.send_message(
                "❌ Boti se giveaway účastnit nemohou.",
                ephemeral=True,
            )
            return

        try:
            joined = self.service.add_entry(self.giveaway_id, interaction.user.id)
            if joined:
                response = "✅ Byl/a jsi zařazen/a do giveaway."
            else:
                self.service.remove_entry(self.giveaway_id, interaction.user.id)
                response = "↩️ Byl/a jsi z giveaway odhlášen/a."

            await interaction.response.send_message(response, ephemeral=True)
            await self.service.update_message(self.giveaway_id)
        except Exception:
            logger.exception("Chyba při změně účasti v giveaway %s.", self.giveaway_id)
            if interaction.response.is_done():
                await interaction.followup.send(
                    "❌ Účast se nepodařilo změnit. Zkus to později.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "❌ Účast se nepodařilo změnit. Zkus to později.",
                    ephemeral=True,
                )
