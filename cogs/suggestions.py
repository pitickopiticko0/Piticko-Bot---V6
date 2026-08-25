"""Komunitní návrhy s hlasováním a moderovaným stavem."""

from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from config import EMBED_COLOR, EMBED_FOOTER
from utils.database import db
from utils.logger import logger


STATUS_LABELS = {
    "open": "🔵 Nový návrh",
    "considering": "🟡 Zvažujeme",
    "accepted": "🟢 Přijato",
    "rejected": "🔴 Zamítnuto",
    "done": "✅ Hotovo",
}
FINAL_STATUSES = {"rejected", "done"}


class SuggestionVoteView(discord.ui.View):
    def __init__(self, cog: "Suggestions", suggestion_id: int, *, disabled: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        self.suggestion_id = suggestion_id
        for label, emoji, value, style in (
            ("Pro", "👍", 1, discord.ButtonStyle.success),
            ("Proti", "👎", -1, discord.ButtonStyle.secondary),
        ):
            button = discord.ui.Button(
                label=label,
                emoji=emoji,
                style=style,
                disabled=disabled,
                custom_id=f"suggestion:vote:{suggestion_id}:{value}",
            )

            async def callback(interaction: discord.Interaction, vote_value: int = value) -> None:
                await self.cog.cast_vote(interaction, self.suggestion_id, vote_value)

            button.callback = callback
            self.add_item(button)


class SuggestionModal(discord.ui.Modal, title="Poslat návrh"):
    title_input = discord.ui.TextInput(
        label="Název návrhu", max_length=120, placeholder="Např. Přidat kanál pro CS2"
    )
    description_input = discord.ui.TextInput(
        label="Popis a důvod", style=discord.TextStyle.paragraph, max_length=1500,
        placeholder="Vysvětli stručně, co navrhuješ a proč by to komunitě pomohlo.",
    )

    def __init__(self, cog: "Suggestions"):
        super().__init__(custom_id="suggestion:modal")
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.submit_suggestion(
            interaction, str(self.title_input), str(self.description_input)
        )


class SuggestionSubmitView(discord.ui.View):
    def __init__(self, cog: "Suggestions"):
        super().__init__(timeout=None)
        self.cog = cog
        button = discord.ui.Button(
            label="Poslat návrh", emoji="💡", style=discord.ButtonStyle.primary,
            custom_id="suggestion:open-modal",
        )
        button.callback = self.open_modal
        self.add_item(button)

    async def open_modal(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Tento panel funguje jen na serveru.", ephemeral=True)
            return
        settings = await asyncio.to_thread(db.get_suggestion_settings, interaction.guild.id)
        if not settings["enabled"]:
            await interaction.response.send_message("❌ Návrhy na tomto serveru nejsou zapnuté.", ephemeral=True)
            return
        await interaction.response.send_modal(SuggestionModal(self.cog))


class Suggestions(commands.GroupCog, name="navrh"):
    """Sbírá a transparentně zobrazuje nápady členů serveru."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(SuggestionSubmitView(self))
        for suggestion in await asyncio.to_thread(db.get_open_suggestions):
            self.bot.add_view(SuggestionVoteView(self, int(suggestion["id"])))

    @staticmethod
    def build_embed(suggestion, upvotes: int, downvotes: int) -> discord.Embed:
        status = str(suggestion["status"])
        embed = discord.Embed(
            title=f"💡 Návrh #{suggestion['id']}: {suggestion['title']}",
            description=str(suggestion["description"])[:4000],
            color=EMBED_COLOR,
        )
        embed.add_field(name="Stav", value=STATUS_LABELS.get(status, status), inline=True)
        embed.add_field(name="Hlasování", value=f"👍 **{upvotes}**  •  👎 **{downvotes}**", inline=True)
        response = str(suggestion["moderator_response"] or "").strip()
        if response:
            embed.add_field(name="Vyjádření týmu", value=response[:1024], inline=False)
        embed.set_footer(text=f"Autor: {suggestion['author_id']} • {EMBED_FOOTER}")
        return embed

    async def _get_channel(self, guild: discord.Guild, channel_id: int) -> discord.TextChannel | None:
        channel = guild.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return None
        return channel if isinstance(channel, discord.TextChannel) else None

    async def _refresh_message(self, suggestion_id: int) -> None:
        suggestion = await asyncio.to_thread(db.get_suggestion, suggestion_id)
        if suggestion is None or not suggestion["message_id"]:
            return
        guild = self.bot.get_guild(int(suggestion["guild_id"]))
        channel = await self._get_channel(guild, int(suggestion["channel_id"])) if guild else None
        if channel is None:
            return
        try:
            message = await channel.fetch_message(int(suggestion["message_id"]))
            upvotes, downvotes = await asyncio.to_thread(db.get_suggestion_vote_totals, suggestion_id)
            final = str(suggestion["status"]) in FINAL_STATUSES
            await message.edit(
                embed=self.build_embed(suggestion, upvotes, downvotes),
                view=SuggestionVoteView(self, suggestion_id, disabled=final),
            )
        except (discord.NotFound, discord.Forbidden):
            return
        except discord.HTTPException:
            logger.exception("Návrh %s se nepodařilo aktualizovat.", suggestion_id)

    async def submit_suggestion(
        self, interaction: discord.Interaction, title: str, description: str
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Návrhy lze posílat jen na serveru.", ephemeral=True)
            return
        safe_title = " ".join(title.split())[:120]
        safe_description = description.strip()[:1500]
        if len(safe_title) < 3 or len(safe_description) < 10:
            await interaction.response.send_message(
                "❌ Napiš výstižný název a alespoň krátké vysvětlení návrhu.", ephemeral=True
            )
            return
        settings = await asyncio.to_thread(db.get_suggestion_settings, interaction.guild.id)
        if not settings["enabled"] or not settings["channel_id"].isdigit():
            await interaction.response.send_message("❌ Návrhy zatím nejsou na tomto serveru nastavené.", ephemeral=True)
            return
        channel = await self._get_channel(interaction.guild, int(settings["channel_id"]))
        permissions = channel.permissions_for(interaction.guild.me) if channel and interaction.guild.me else None
        if not channel or not permissions or not (permissions.view_channel and permissions.send_messages and permissions.embed_links):
            await interaction.response.send_message("❌ Bot nemůže poslat návrh do nastaveného kanálu.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        suggestion_id = await asyncio.to_thread(
            db.create_suggestion, interaction.guild.id, channel.id, interaction.user.id, safe_title, safe_description
        )
        suggestion = await asyncio.to_thread(db.get_suggestion, suggestion_id)
        try:
            message = await channel.send(
                embed=self.build_embed(suggestion, 0, 0),
                view=SuggestionVoteView(self, suggestion_id),
            )
        except discord.HTTPException:
            logger.exception("Návrh %s se nepodařilo odeslat.", suggestion_id)
            await interaction.followup.send("❌ Návrh se nepodařilo odeslat do kanálu.", ephemeral=True)
            return
        await asyncio.to_thread(db.set_suggestion_message_id, suggestion_id, message.id)
        self.bot.add_view(SuggestionVoteView(self, suggestion_id))
        await interaction.followup.send(f"✅ Návrh byl odeslán do {channel.mention}.", ephemeral=True)

    async def cast_vote(self, interaction: discord.Interaction, suggestion_id: int, value: int) -> None:
        suggestion = await asyncio.to_thread(db.get_suggestion, suggestion_id)
        if suggestion is None or str(suggestion["status"]) in FINAL_STATUSES:
            await interaction.response.send_message("❌ Pro tento návrh už nelze hlasovat.", ephemeral=True)
            return
        if interaction.guild is None or interaction.guild.id != int(suggestion["guild_id"]):
            await interaction.response.send_message("❌ Tento návrh patří na jiný server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        upvotes, downvotes = await asyncio.to_thread(
            db.vote_suggestion, suggestion_id, interaction.user.id, value
        )
        await self._refresh_message(suggestion_id)
        choice = "pro" if value == 1 else "proti"
        await interaction.followup.send(
            f"✅ Hlas **{choice}** uložen. Aktuálně: 👍 {upvotes} • 👎 {downvotes}.", ephemeral=True
        )

    @app_commands.command(name="poslat", description="Otevře formulář pro odeslání návrhu.")
    async def send(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Tento příkaz funguje jen na serveru.", ephemeral=True)
            return
        settings = await asyncio.to_thread(db.get_suggestion_settings, interaction.guild.id)
        if not settings["enabled"]:
            await interaction.response.send_message("❌ Návrhy na tomto serveru nejsou zapnuté.", ephemeral=True)
            return
        await interaction.response.send_modal(SuggestionModal(self))

    @app_commands.command(name="panel", description="Odešle tlačítko pro vytvoření návrhu.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def panel(self, interaction: discord.Interaction, kanal: discord.TextChannel) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("❌ Tento příkaz funguje jen na serveru.", ephemeral=True)
            return
        settings = await asyncio.to_thread(db.get_suggestion_settings, interaction.guild.id)
        if not settings["enabled"]:
            await interaction.response.send_message("❌ Nejdřív zapni návrhy v dashboardu.", ephemeral=True)
            return
        me = interaction.guild.me
        permissions = kanal.permissions_for(me) if me else None
        if not permissions or not (permissions.view_channel and permissions.send_messages and permissions.embed_links):
            await interaction.response.send_message("❌ Bot do tohoto kanálu nemůže posílat zprávy.", ephemeral=True)
            return
        embed = discord.Embed(
            title="💡 Máš nápad na zlepšení?",
            description="Klikni na tlačítko, popiš svůj návrh a komunita o něm může hlasovat.",
            color=EMBED_COLOR,
        )
        embed.set_footer(text=EMBED_FOOTER)
        await kanal.send(embed=embed, view=SuggestionSubmitView(self))
        await interaction.response.send_message(f"✅ Panel byl odeslán do {kanal.mention}.", ephemeral=True)

    @app_commands.command(name="stav", description="Změní stav návrhu a přidá vyjádření týmu.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.choices(stav=[
        app_commands.Choice(name="🟡 Zvažujeme", value="considering"),
        app_commands.Choice(name="🟢 Přijato", value="accepted"),
        app_commands.Choice(name="🔴 Zamítnuto", value="rejected"),
        app_commands.Choice(name="✅ Hotovo", value="done"),
    ])
    async def status(
        self, interaction: discord.Interaction, cislo: app_commands.Range[int, 1],
        stav: app_commands.Choice[str], vyjadreni: str = ""
    ) -> None:
        suggestion = await asyncio.to_thread(db.get_suggestion, int(cislo))
        if interaction.guild is None or suggestion is None or int(suggestion["guild_id"]) != interaction.guild.id:
            await interaction.response.send_message("❌ Návrh na tomto serveru nebyl nalezen.", ephemeral=True)
            return
        await asyncio.to_thread(
            db.set_suggestion_status, int(cislo), stav.value, interaction.user.id, vyjadreni
        )
        await self._refresh_message(int(cislo))
        await interaction.response.send_message(
            f"✅ Návrh #{cislo} má nyní stav **{stav.name}**.", ephemeral=True
        )

    @app_commands.command(name="info", description="Zobrazí aktuální stav návrhu.")
    async def info(self, interaction: discord.Interaction, cislo: app_commands.Range[int, 1]) -> None:
        suggestion = await asyncio.to_thread(db.get_suggestion, int(cislo))
        if interaction.guild is None or suggestion is None or int(suggestion["guild_id"]) != interaction.guild.id:
            await interaction.response.send_message("❌ Návrh na tomto serveru nebyl nalezen.", ephemeral=True)
            return
        upvotes, downvotes = await asyncio.to_thread(db.get_suggestion_vote_totals, int(cislo))
        await interaction.response.send_message(
            embed=self.build_embed(suggestion, upvotes, downvotes), ephemeral=True
        )

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            message = "❌ Tento příkaz může použít pouze správce serveru."
        else:
            logger.exception("Chyba příkazu návrhů: %s", error)
            message = "❌ Nastala chyba při práci s návrhy."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Suggestions(bot))
