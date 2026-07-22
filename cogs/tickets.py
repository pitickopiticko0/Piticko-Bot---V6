import asyncio
import re
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import EMBED_COLOR, EMBED_FOOTER
from utils.database import db
from utils.logger import logger


def clean_name(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:40] or "user"


class TicketModal(discord.ui.Modal, title="Vytvořit ticket"):
    subject = discord.ui.TextInput(
        label="Předmět",
        placeholder="Například: Technický problém",
        min_length=3,
        max_length=100,
    )
    description = discord.ui.TextInput(
        label="Popis problému",
        placeholder="Popiš problém co nejpodrobněji.",
        style=discord.TextStyle.paragraph,
        min_length=10,
        max_length=1500,
    )

    def __init__(self, cog: "Tickets"):
        super().__init__(timeout=300)
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.create_ticket(
            interaction,
            str(self.subject),
            str(self.description),
        )


class CreateTicketView(discord.ui.View):
    def __init__(self, cog: "Tickets"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Vytvořit ticket",
        emoji="🎫",
        style=discord.ButtonStyle.success,
        custom_id="piticko:ticket:create",
    )
    async def create_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Ticket lze vytvořit pouze na serveru.",
                ephemeral=True,
            )
            return

        settings = self.cog.get_settings(interaction.guild.id)

        if settings is None or not settings["enabled"]:
            await interaction.response.send_message(
                "❌ Ticket systém není zapnutý.",
                ephemeral=True,
            )
            return

        existing = self.cog.get_open_ticket(
            interaction.guild.id,
            interaction.user.id,
        )

        if existing:
            channel = interaction.guild.get_channel(int(existing["channel_id"]))
            text = f"❌ Už máš otevřený ticket: {channel.mention}" if channel else "❌ Už máš otevřený ticket."
            await interaction.response.send_message(text, ephemeral=True)
            return

        await interaction.response.send_modal(TicketModal(self.cog))

    @discord.ui.button(
        label="Jak fungují tickety?",
        emoji="📖",
        style=discord.ButtonStyle.secondary,
        custom_id="piticko:ticket:help",
    )
    async def ticket_help(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        embed = discord.Embed(
            title="📖 Jak vytvořit ticket?",
            description=(
                "Ticket je soukromý kanál mezi tebou a support týmem.\n\n"
                "**Postup:**\n"
                "1️⃣ Klikni na **🎫 Vytvořit ticket**.\n"
                "2️⃣ Vyplň předmět a popis problému.\n"
                "3️⃣ Odešli formulář.\n"
                "4️⃣ Bot vytvoří soukromý kanál.\n"
                "5️⃣ Počkej na odpověď supportu."
            ),
            color=EMBED_COLOR,
        )
        embed.add_field(
            name="✅ Co napsat do ticketu",
            value=(
                "• Co přesně nefunguje\n"
                "• Jaká chyba se zobrazuje\n"
                "• Co už jsi zkoušel\n"
                "• Screenshot, pokud pomůže"
            ),
            inline=False,
        )
        embed.add_field(
            name="🔒 Kdo ticket uvidí?",
            value=(
                "👤 Ty\n"
                "👮 Support tým\n"
                "👑 Administrátoři\n\n"
                "Ostatní členové serveru ticket neuvidí."
            ),
            inline=False,
        )
        embed.add_field(
            name="⚠️ Důležité",
            value=(
                "Jeden uživatel může mít otevřený pouze **jeden ticket**.\n"
                "Nevytvářej ticket kvůli spamu nebo trollení."
            ),
            inline=False,
        )
        embed.set_footer(text=EMBED_FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TicketControls(discord.ui.View):
    def __init__(self, cog: "Tickets"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Převzít",
        emoji="🙋",
        style=discord.ButtonStyle.primary,
        custom_id="piticko:ticket:claim",
    )
    async def claim(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await self.cog.claim_ticket(interaction)

    @discord.ui.button(
        label="Zavřít",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="piticko:ticket:close",
    )
    async def close(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await self.cog.close_ticket(interaction)


class Tickets(commands.GroupCog, name="ticket"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(CreateTicketView(self))
        self.bot.add_view(TicketControls(self))

    def get_settings(self, guild_id: int):
        return db.get_ticket_settings(guild_id)

    def get_open_ticket(self, guild_id: int, user_id: int):
        return db.get_open_ticket(guild_id, user_id)

    def get_ticket_by_channel(self, channel_id: int):
        return db.get_ticket_by_channel(channel_id)

    def save_settings(
        self,
        guild_id: int,
        panel_channel_id: int,
        category_id: int,
        support_role_id: int,
        log_channel_id: Optional[int],
    ):
        db.set_ticket_settings(
            guild_id,
            panel_channel_id,
            category_id,
            support_role_id,
            log_channel_id,
            enabled=True,
        )

    def is_support(self, member: discord.Member, settings) -> bool:
        return (
            member.guild_permissions.administrator
            or any(role.id == int(settings["support_role_id"]) for role in member.roles)
        )

    async def create_ticket(
        self,
        interaction: discord.Interaction,
        subject: str,
        description: str,
    ):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return

        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        settings = self.get_settings(guild.id)

        if settings is None:
            await interaction.followup.send("❌ Ticket systém není nastavený.", ephemeral=True)
            return

        category = guild.get_channel(int(settings["category_id"]))
        support_role = guild.get_role(int(settings["support_role_id"]))
        bot_member = guild.me

        if not isinstance(category, discord.CategoryChannel) or support_role is None or bot_member is None:
            await interaction.followup.send("❌ Kategorie, role nebo bot nebyli nalezeni.", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            ),
            support_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            ),
            bot_member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True,
            ),
        }

        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{clean_name(interaction.user.display_name)}-{str(interaction.user.id)[-4:]}",
                category=category,
                overwrites=overwrites,
                topic=f"Ticket uživatele {interaction.user.id}",
                reason="Piticko Bot ticket",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Bot nemá oprávnění vytvářet kanály.",
                ephemeral=True,
            )
            return

        db.create_ticket_record(
            guild.id,
            channel.id,
            interaction.user.id,
            subject,
            description,
        )

        embed = discord.Embed(
            title=f"🎫 {subject}",
            description=description,
            color=EMBED_COLOR,
        )
        embed.add_field(name="Autor", value=interaction.user.mention, inline=True)
        embed.add_field(name="Stav", value="🟢 Otevřený", inline=True)
        embed.set_footer(text=EMBED_FOOTER)

        await channel.send(
            content=f"{interaction.user.mention} {support_role.mention}",
            embed=embed,
            view=TicketControls(self),
        )

        await interaction.followup.send(
            f"✅ Ticket byl vytvořen: {channel.mention}",
            ephemeral=True,
        )

    async def claim_ticket(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.channel is None or not isinstance(interaction.user, discord.Member):
            return

        settings = self.get_settings(interaction.guild.id)
        ticket = self.get_ticket_by_channel(interaction.channel.id)

        if settings is None or ticket is None:
            await interaction.response.send_message("❌ Toto není aktivní ticket.", ephemeral=True)
            return

        if not self.is_support(interaction.user, settings):
            await interaction.response.send_message("❌ Ticket může převzít pouze support.", ephemeral=True)
            return

        db.claim_ticket_record(interaction.channel.id, interaction.user.id)

        await interaction.response.send_message(
            f"🙋 Ticket převzal {interaction.user.mention}.",
        )

    async def close_ticket(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.channel is None or not isinstance(interaction.user, discord.Member):
            return

        settings = self.get_settings(interaction.guild.id)
        ticket = self.get_ticket_by_channel(interaction.channel.id)

        if settings is None or ticket is None:
            await interaction.response.send_message("❌ Toto není aktivní ticket.", ephemeral=True)
            return

        if interaction.user.id != int(ticket["user_id"]) and not self.is_support(interaction.user, settings):
            await interaction.response.send_message("❌ Nemáš oprávnění ticket zavřít.", ephemeral=True)
            return

        await interaction.response.send_message("🔒 Ticket se za 5 sekund zavře.")

        db.close_ticket_record(interaction.channel.id)

        await asyncio.sleep(5)
        await interaction.channel.delete(reason=f"Ticket zavřel {interaction.user}")

    @app_commands.command(name="setup", description="Nastaví ticket systém.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(
        self,
        interaction: discord.Interaction,
        panel_channel: discord.TextChannel,
        category: discord.CategoryChannel,
        support_role: discord.Role,
        log_channel: Optional[discord.TextChannel] = None,
    ):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            return

        db.add_guild(interaction.guild.id, interaction.guild.name)

        self.save_settings(
            interaction.guild.id,
            panel_channel.id,
            category.id,
            support_role.id,
            log_channel.id if log_channel else None,
        )

        await interaction.followup.send(
            "✅ Ticket systém byl nastaven. Teď použij `/ticket panel`.",
            ephemeral=True,
        )

    @app_commands.command(name="panel", description="Odešle ticket panel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            return

        settings = self.get_settings(interaction.guild.id)

        if settings is None:
            await interaction.followup.send("❌ Nejprve použij `/ticket setup`.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(int(settings["panel_channel_id"]))

        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("❌ Panel kanál nebyl nalezen.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎫 Potřebuješ pomoc?",
            description=(
                "**Vytvoření ticketu je jednoduché:**\n\n"
                "1️⃣ Klikni na tlačítko **🎫 Vytvořit ticket**.\n"
                "2️⃣ Vyplň krátký formulář.\n"
                "3️⃣ Odešli formulář.\n"
                "4️⃣ Bot vytvoří soukromý kanál pouze pro tebe a support.\n"
                "5️⃣ Počkej na odpověď support týmu."
            ),
            color=EMBED_COLOR,
        )
        embed.add_field(
            name="📋 Před vytvořením ticketu",
            value=(
                "• Popiš problém co nejpodrobněji.\n"
                "• Přilož screenshot, pokud pomůže.\n"
                "• Nevytvářej více ticketů najednou.\n"
                "• Jeden uživatel může mít otevřený pouze **1 ticket**."
            ),
            inline=False,
        )
        embed.add_field(
            name="🔒 Kdo ticket uvidí?",
            value=(
                "👤 Ty\n"
                "👮 Support tým\n"
                "👑 Administrátoři\n\n"
                "❌ Ostatní členové serveru ticket neuvidí."
            ),
            inline=False,
        )
        embed.add_field(
            name="✅ Po vyřešení",
            value=(
                "Jakmile bude problém vyřešen, klikni na "
                "**🔒 Zavřít**, nebo ticket uzavře support."
            ),
            inline=False,
        )
        embed.set_footer(text=EMBED_FOOTER)

        await channel.send(embed=embed, view=CreateTicketView(self))
        await interaction.followup.send(
            f"✅ Ticket panel byl odeslán do {channel.mention}.",
            ephemeral=True,
        )

    @app_commands.command(name="info", description="Zobrazí ticket nastavení.")
    async def info(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            return

        settings = self.get_settings(interaction.guild.id)

        if settings is None:
            await interaction.followup.send("📭 Ticket systém není nastavený.", ephemeral=True)
            return

        panel = interaction.guild.get_channel(int(settings["panel_channel_id"]))
        category = interaction.guild.get_channel(int(settings["category_id"]))
        support = interaction.guild.get_role(int(settings["support_role_id"]))

        embed = discord.Embed(title="🎫 Ticket nastavení", color=EMBED_COLOR)
        embed.add_field(name="Panel", value=panel.mention if panel else "Nenalezen", inline=True)
        embed.add_field(name="Kategorie", value=category.name if category else "Nenalezena", inline=True)
        embed.add_field(name="Support", value=support.mention if support else "Nenalezena", inline=True)
        embed.set_footer(text=EMBED_FOOTER)

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
