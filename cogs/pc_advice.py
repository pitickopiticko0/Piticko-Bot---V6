import asyncio
import json
import re
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import EMBED_COLOR, EMBED_FOOTER
from utils.database import db
from utils.logger import logger
from utils.pc_advice_validation import validate_advice_answers


REQUEST_TYPES = {
    "build": {
        "label": "Nová PC sestava",
        "emoji": "🖥️",
        "questions": (
            ("Rozpočet", "Například 35 000 Kč včetně/neobsahuje monitor", False),
            ("Použití a programy", "Hry, práce, střih, streamování…", True),
            ("Monitor a cílový výkon", "Například 1440p, 165 Hz, monitor už mám", False),
            ("Preference a vzhled", "AMD/Intel/NVIDIA, RGB, velikost skříně…", True),
            ("Co už vlastníš a termín", "Komponenty, které chceš použít, a kdy nakupuješ", True),
        ),
    },
    "upgrade": {
        "label": "Upgrade počítače",
        "emoji": "🔧",
        "questions": (
            ("Současný procesor a deska", "Přesný model CPU a základní desky", False),
            ("Grafika, RAM a zdroj", "Přesné modely a výkon zdroje", True),
            ("Skříň, chlazení a disky", "Modely nebo alespoň rozměry", True),
            ("Co chceš zlepšit", "Hry, programy, rozlišení a současný problém", True),
            ("Rozpočet a termín", "Kolik chceš utratit a kdy budeš nakupovat", False),
        ),
    },
    "diagnostics": {
        "label": "Diagnostika problému",
        "emoji": "🩺",
        "questions": (
            ("Popis problému", "Co přesně se děje a kdy problém začal", True),
            ("Chybová hláška", "Přesné znění chyby, případně napiš Bez chyby", True),
            ("Konfigurace počítače", "CPU, GPU, deska, RAM, zdroj a systém", True),
            ("Co už jsi vyzkoušel", "Restart, ovladače, kabely, testy…", True),
            ("Kdy problém nastává", "Při startu, ve hře, v zátěži, náhodně…", True),
        ),
    },
}

def clean_name(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:32] or "uzivatel"


class AdviceModal(discord.ui.Modal):
    def __init__(
        self, cog: "PCAdvice", request_type: str, selected_mode: str | None = None
    ):
        definition = REQUEST_TYPES[request_type]
        super().__init__(title=definition["label"], timeout=600)
        self.cog = cog
        self.request_type = request_type
        self.selected_mode = selected_mode
        self.inputs: list[tuple[str, discord.ui.TextInput]] = []
        for label, placeholder, paragraph in definition["questions"]:
            item = discord.ui.TextInput(
                label=label,
                placeholder=placeholder,
                style=discord.TextStyle.paragraph if paragraph else discord.TextStyle.short,
                min_length=2,
                max_length=1000 if paragraph else 250,
                required=True,
            )
            self.inputs.append((label, item))
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        answers = {label: str(item).strip() for label, item in self.inputs}
        await self.cog.create_request(
            interaction, self.request_type, answers, self.selected_mode
        )


class AdvicePrivacyChoice(discord.ui.View):
    def __init__(self, cog: "PCAdvice", request_type: str):
        super().__init__(timeout=180)
        self.cog = cog
        self.request_type = request_type

    @discord.ui.button(label="Soukromě", emoji="🔒", style=discord.ButtonStyle.primary)
    async def private(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            AdviceModal(self.cog, self.request_type, "private")
        )

    @discord.ui.button(label="Veřejně ve fóru", emoji="👁️", style=discord.ButtonStyle.secondary)
    async def forum(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            AdviceModal(self.cog, self.request_type, "forum")
        )


class AdviceTypeSelect(discord.ui.Select):
    def __init__(self, cog: "PCAdvice"):
        self.cog = cog
        super().__init__(
            placeholder="Vyber typ PC poradny…",
            min_values=1,
            max_values=1,
            custom_id="piticko:pc_advice:type",
            options=[
                discord.SelectOption(
                    label=data["label"], value=key, emoji=data["emoji"],
                    description={
                        "build": "Navrhneme sestavu podle rozpočtu a využití.",
                        "upgrade": "Prověříme smysluplný upgrade současného PC.",
                        "diagnostics": "Pomůžeme najít příčinu technického problému.",
                    }[key],
                )
                for key, data in REQUEST_TYPES.items()
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ PC poradna funguje pouze na serveru.", ephemeral=True
            )
            return
        settings = self.cog.get_settings(interaction.guild.id)
        if settings is None or not settings["enabled"]:
            await interaction.response.send_message(
                "❌ PC poradna není zapnutá.", ephemeral=True
            )
            return
        existing = db.get_active_pc_advice(interaction.guild.id, interaction.user.id)
        if existing:
            channel = interaction.guild.get_channel(int(existing["channel_id"]))
            message = (
                f"❌ Už máš aktivní požadavek: {channel.mention}"
                if channel else "❌ Už máš aktivní požadavek."
            )
            await interaction.response.send_message(message, ephemeral=True)
            return
        if str(settings["mode"] or "private") == "choice":
            await interaction.response.send_message(
                "Vyber, kdo bude moct tvůj požadavek zobrazit:",
                view=AdvicePrivacyChoice(self.cog, self.values[0]),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(AdviceModal(self.cog, self.values[0]))


class AdvicePanel(discord.ui.View):
    def __init__(self, cog: "PCAdvice"):
        super().__init__(timeout=None)
        self.add_item(AdviceTypeSelect(cog))


class AdviceControls(discord.ui.View):
    def __init__(self, cog: "PCAdvice"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Převzít", emoji="🙋", style=discord.ButtonStyle.primary,
        custom_id="piticko:pc_advice:claim",
    )
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.claim_request(interaction)

    @discord.ui.button(
        label="Čeká na uživatele", emoji="⏳", style=discord.ButtonStyle.secondary,
        custom_id="piticko:pc_advice:waiting_user",
    )
    async def waiting_user(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.cog.wait_for_user(interaction)

    @discord.ui.button(
        label="Vyřešeno", emoji="✅", style=discord.ButtonStyle.success,
        custom_id="piticko:pc_advice:resolve",
    )
    async def resolve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.resolve_request(interaction)

    @discord.ui.button(
        label="Zavřít", emoji="🔒", style=discord.ButtonStyle.danger,
        custom_id="piticko:pc_advice:close",
    )
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.close_request(interaction)


class PCAdvice(commands.GroupCog, group_name="pcporadna"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(AdvicePanel(self))
        self.bot.add_view(AdviceControls(self))

    @staticmethod
    def get_settings(guild_id: int):
        return db.get_pc_advice_settings(guild_id)

    @staticmethod
    def is_advisor(member: discord.Member, settings) -> bool:
        return (
            member.guild_permissions.administrator
            or any(role.id == int(settings["advisor_role_id"]) for role in member.roles)
        )

    @staticmethod
    def forum_tags(
        forum: discord.ForumChannel, *names: str
    ) -> list[discord.ForumTag]:
        wanted = {name.casefold() for name in names}
        return [tag for tag in forum.available_tags if tag.name.casefold() in wanted][:5]

    async def update_forum_status(
        self, channel: discord.abc.GuildChannel | discord.Thread, status: str
    ) -> None:
        if not isinstance(channel, discord.Thread):
            return
        forum = channel.parent
        if not isinstance(forum, discord.ForumChannel):
            return
        status_names = {
            "čeká na poradce", "řeší se", "čeká na uživatele", "vyřešeno"
        }
        kept = [
            tag for tag in channel.applied_tags
            if tag.name.casefold() not in status_names
        ]
        replacement = self.forum_tags(forum, status)
        try:
            await channel.edit(applied_tags=(kept + replacement)[:5])
        except discord.HTTPException:
            logger.exception("Aktualizace štítku PC poradny selhala.")

    async def create_request(
        self,
        interaction: discord.Interaction,
        request_type: str,
        answers: dict[str, str],
        selected_mode: str | None = None,
    ) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return
        validation_errors = validate_advice_answers(request_type, answers)
        if validation_errors:
            await interaction.response.send_message(
                "❌ Požadavek nelze vytvořit. Oprav formulář:\n"
                + "\n".join(f"• {error}" for error in validation_errors[:5])
                + "\n\nPotom formulář odešli znovu.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        settings = self.get_settings(guild.id)
        if settings is None or not settings["enabled"]:
            await interaction.followup.send("❌ PC poradna není zapnutá.", ephemeral=True)
            return
        if db.get_active_pc_advice(guild.id, interaction.user.id):
            await interaction.followup.send("❌ Už máš aktivní požadavek.", ephemeral=True)
            return

        advisor_role = guild.get_role(int(settings["advisor_role_id"]))
        configured_mode = str(settings["mode"] or "private")
        mode = selected_mode if configured_mode == "choice" else configured_mode
        if mode not in {"private", "forum"}:
            await interaction.followup.send(
                "❌ Nebyl vybrán platný režim poradny.", ephemeral=True
            )
            return
        destination_id = (
            settings["forum_channel_id"]
            if mode == "forum"
            else settings["category_id"]
        )
        destination = guild.get_channel(int(destination_id))
        if advisor_role is None or guild.me is None:
            await interaction.followup.send(
                "❌ Role poradců nebo bot nejsou dostupní.", ephemeral=True
            )
            return
        definition = REQUEST_TYPES[request_type]
        embed = discord.Embed(
            title=f"{definition['emoji']} {definition['label']}",
            description="Níže najdeš všechny informace, které uživatel vyplnil.",
            color=EMBED_COLOR,
        )
        embed.add_field(name="Autor", value=interaction.user.mention, inline=True)
        embed.add_field(name="Stav", value="🟢 Otevřený", inline=True)
        for label, value in answers.items():
            embed.add_field(name=label, value=value[:1024], inline=False)
        embed.set_footer(text=EMBED_FOOTER)
        content = f"{interaction.user.mention} {advisor_role.mention}"
        allowed_mentions = discord.AllowedMentions(
            users=True, roles=True, everyone=False
        )
        try:
            if mode == "forum":
                if not isinstance(destination, discord.ForumChannel):
                    await interaction.followup.send(
                        "❌ Nastavené fórum nebylo nalezeno.", ephemeral=True
                    )
                    return
                post_name = (
                    f"[{definition['label']}] "
                    f"{interaction.user.display_name}"
                )[:100]
                tags = self.forum_tags(
                    destination, definition["label"], "Čeká na poradce"
                )
                if (
                    not tags
                    and destination.flags.require_tag
                    and destination.available_tags
                ):
                    tags = [destination.available_tags[0]]
                created = await destination.create_thread(
                    name=post_name,
                    content=content,
                    embed=embed,
                    view=AdviceControls(self),
                    applied_tags=tags,
                    allowed_mentions=allowed_mentions,
                    reason="Piticko Bot PC poradna",
                )
                channel = created.thread
            else:
                if not isinstance(destination, discord.CategoryChannel):
                    await interaction.followup.send(
                        "❌ Kategorie PC poradny nebyla nalezena.", ephemeral=True
                    )
                    return
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    interaction.user: discord.PermissionOverwrite(
                        view_channel=True, send_messages=True, read_message_history=True,
                        attach_files=True, embed_links=True,
                    ),
                    advisor_role: discord.PermissionOverwrite(
                        view_channel=True, send_messages=True, read_message_history=True,
                    ),
                    guild.me: discord.PermissionOverwrite(
                        view_channel=True, send_messages=True, read_message_history=True,
                        manage_channels=True, manage_messages=True,
                    ),
                }
                channel = await guild.create_text_channel(
                    name=f"pc-{request_type}-{clean_name(interaction.user.display_name)}",
                    category=destination,
                    overwrites=overwrites,
                    topic=f"PC poradna | {request_type} | uživatel {interaction.user.id}",
                    reason="Piticko Bot PC poradna",
                )
                await channel.send(
                    content=content,
                    embed=embed,
                    view=AdviceControls(self),
                    allowed_mentions=allowed_mentions,
                )
        except (discord.Forbidden, discord.HTTPException):
            logger.exception("Vytvoření požadavku PC poradny selhalo.")
            await interaction.followup.send(
                "❌ Bot nemůže vytvořit požadavek poradny.", ephemeral=True
            )
            return
        db.create_pc_advice_request(
            guild.id, channel.id, interaction.user.id, request_type, answers,
        )
        await interaction.followup.send(
            f"✅ Požadavek byl vytvořen: {channel.mention}\n"
            + (
                "ℹ️ Tento příspěvek je veřejný pro členy, kteří vidí fórum."
                if mode == "forum" else ""
            ),
            ephemeral=True,
        )

    async def _context(self, interaction: discord.Interaction):
        if (
            interaction.guild is None
            or interaction.channel is None
            or not isinstance(interaction.user, discord.Member)
        ):
            return None, None
        return (
            self.get_settings(interaction.guild.id),
            db.get_pc_advice_by_channel(interaction.channel.id),
        )

    @staticmethod
    async def update_request_embed_status(
        interaction: discord.Interaction, status: str
    ) -> None:
        message = interaction.message
        if message is None or not message.embeds:
            logger.warning(
                "PC poradna: původní zpráva pro změnu stavu nebyla nalezena."
            )
            return

        embed = message.embeds[0].copy()
        for index, field in enumerate(embed.fields):
            if field.name.casefold() == "stav":
                embed.set_field_at(
                    index,
                    name=field.name,
                    value=status,
                    inline=field.inline,
                )
                break
        else:
            embed.add_field(name="Stav", value=status, inline=True)

        try:
            await message.edit(embed=embed)
        except discord.HTTPException:
            logger.exception("Aktualizace stavu v embedu PC poradny selhala.")

    async def claim_request(self, interaction: discord.Interaction) -> None:
        settings, request = await self._context(interaction)
        if settings is None or request is None or request["status"] == "closed":
            await interaction.response.send_message(
                "❌ Toto není aktivní požadavek PC poradny.", ephemeral=True
            )
            return
        if not self.is_advisor(interaction.user, settings):
            await interaction.response.send_message(
                "❌ Požadavek může převzít pouze poradce.", ephemeral=True
            )
            return
        if request["claimed_by"]:
            await interaction.response.send_message(
                f"ℹ️ Požadavek už převzal <@{request['claimed_by']}>.", ephemeral=True
            )
            return
        await interaction.response.defer()
        db.claim_pc_advice(interaction.channel.id, interaction.user.id)
        await self.update_forum_status(interaction.channel, "Řeší se")
        await self.update_request_embed_status(interaction, "🔵 Řeší se")
        await interaction.followup.send(
            f"🙋 Požadavek převzal {interaction.user.mention}."
        )

    async def resolve_request(self, interaction: discord.Interaction) -> None:
        settings, request = await self._context(interaction)
        if settings is None or request is None or request["status"] == "closed":
            await interaction.response.send_message(
                "❌ Toto není aktivní požadavek PC poradny.", ephemeral=True
            )
            return
        if not self.is_advisor(interaction.user, settings):
            await interaction.response.send_message(
                "❌ Jako vyřešené jej může označit pouze poradce.", ephemeral=True
            )
            return
        await interaction.response.defer()
        db.resolve_pc_advice(interaction.channel.id)
        await self.update_forum_status(interaction.channel, "Vyřešeno")
        await self.update_request_embed_status(interaction, "✅ Vyřešeno")
        await interaction.followup.send(
            f"✅ Požadavek označil {interaction.user.mention} jako vyřešený."
        )

    async def wait_for_user(self, interaction: discord.Interaction) -> None:
        settings, request = await self._context(interaction)
        if settings is None or request is None or request["status"] == "closed":
            await interaction.response.send_message(
                "❌ Toto není aktivní požadavek PC poradny.", ephemeral=True
            )
            return
        if not self.is_advisor(interaction.user, settings):
            await interaction.response.send_message(
                "❌ Na odpověď uživatele může čekat pouze poradce.", ephemeral=True
            )
            return
        if request["status"] == "waiting_user":
            await interaction.response.send_message(
                "ℹ️ Požadavek už čeká na odpověď uživatele.", ephemeral=True
            )
            return
        await interaction.response.defer()
        db.wait_for_pc_advice_user(interaction.channel.id)
        await self.update_forum_status(interaction.channel, "Čeká na uživatele")
        await self.update_request_embed_status(
            interaction, "⏳ Čeká na uživatele"
        )
        await interaction.followup.send(
            f"⏳ <@{request['user_id']}>, poradce {interaction.user.mention} "
            "čeká na tvoji odpověď nebo doplnění informací.",
            allowed_mentions=discord.AllowedMentions(
                users=True, roles=False, everyone=False
            ),
        )

    async def close_request(self, interaction: discord.Interaction) -> None:
        settings, request = await self._context(interaction)
        if settings is None or request is None or request["status"] == "closed":
            await interaction.response.send_message(
                "❌ Toto není aktivní požadavek PC poradny.", ephemeral=True
            )
            return
        owner = interaction.user.id == int(request["user_id"])
        if not owner and not self.is_advisor(interaction.user, settings):
            await interaction.response.send_message(
                "❌ Tento požadavek nemůžeš zavřít.", ephemeral=True
            )
            return
        await interaction.response.send_message("🔒 Požadavek se za 5 sekund zavře.")
        db.close_pc_advice(interaction.channel.id)
        log_channel_id = settings["log_channel_id"]
        if log_channel_id:
            log_channel = interaction.guild.get_channel(int(log_channel_id))
            if isinstance(log_channel, discord.TextChannel):
                definition = REQUEST_TYPES.get(request["request_type"], {})
                try:
                    answers = json.loads(request["answers"])
                except (TypeError, json.JSONDecodeError):
                    answers = {}
                embed = discord.Embed(
                    title="🗃️ Uzavřený požadavek PC poradny",
                    description=definition.get("label", request["request_type"]),
                    color=discord.Color.dark_grey(),
                )
                embed.add_field(name="Uživatel", value=f"<@{request['user_id']}>")
                embed.add_field(name="Uzavřel", value=interaction.user.mention)
                embed.add_field(
                    name="Shrnutí",
                    value="\n".join(f"**{key}:** {value}" for key, value in answers.items())[:1024]
                    or "Bez uložených odpovědí",
                    inline=False,
                )
                try:
                    await log_channel.send(embed=embed)
                except discord.HTTPException:
                    logger.exception("Odeslání logu PC poradny selhalo.")
        await asyncio.sleep(5)
        try:
            if isinstance(interaction.channel, discord.Thread):
                await interaction.channel.edit(archived=True, locked=True)
            else:
                await interaction.channel.delete(
                    reason=f"PC poradnu zavřel {interaction.user}"
                )
        except discord.HTTPException:
            logger.exception("Uzavření kanálu PC poradny selhalo.")

    @app_commands.command(name="setup", description="Nastaví PC poradnu.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_command(
        self, interaction: discord.Interaction, panel: discord.TextChannel,
        poradci: discord.Role,
        kategorie: Optional[discord.CategoryChannel] = None,
        forum: Optional[discord.ForumChannel] = None,
        log: Optional[discord.TextChannel] = None,
    ) -> None:
        if interaction.guild is None:
            return
        if (kategorie is None) == (forum is None):
            await interaction.response.send_message(
                "❌ Vyber právě jednu možnost: kategorii pro soukromý režim, "
                "nebo fórum pro veřejný režim.",
                ephemeral=True,
            )
            return
        destination_id = forum.id if forum else kategorie.id
        db.set_pc_advice_settings(
            interaction.guild.id, panel.id, destination_id, poradci.id,
            log.id if log else None,
            mode="forum" if forum else "private",
            forum_channel_id=forum.id if forum else None,
            enabled=True,
        )
        await interaction.response.send_message(
            "✅ PC poradna nastavena. Použij `/pcporadna panel`.", ephemeral=True
        )

    @app_commands.command(name="panel", description="Odešle panel PC poradny.")
    @app_commands.checks.has_permissions(administrator=True)
    async def panel_command(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Příkaz funguje pouze na serveru.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        settings = self.get_settings(interaction.guild.id)
        if settings is None or not settings["enabled"]:
            await interaction.followup.send(
                "❌ Nejdřív PC poradnu nastav.", ephemeral=True
            )
            return
        channel = interaction.guild.get_channel(int(settings["panel_channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(
                "❌ Kanál panelu nebyl nalezen.", ephemeral=True
            )
            return
        embed = discord.Embed(
            title="🧭 Provedeme tě PC poradnou",
            description=(
                "Nevíš si rady se sestavou, upgradem nebo problémem s počítačem? "
                "Vyber dole, s čím potřebuješ pomoct, a odpověz na několik otázek."
            ),
            color=EMBED_COLOR,
        )
        embed.add_field(
            name="1️⃣ Vyber typ pomoci",
            value=(
                "🖥️ **Nová PC sestava** – návrh podle rozpočtu a využití\n"
                "🔧 **Upgrade počítače** – doporučení vhodných komponent\n"
                "🩺 **Diagnostika problému** – pomoc s hledáním příčiny"
            ),
            inline=False,
        )
        embed.add_field(
            name="2️⃣ Vyplň formulář",
            value=(
                "Připrav si rozpočet, přesné modely komponent a podrobný popis. "
                "Čím více informací uvedeš, tím lépe ti poradíme."
            ),
            inline=False,
        )
        embed.add_field(
            name="3️⃣ Počkej na poradce",
            value=(
                "Po odeslání "
                + (
                    "vytvoříme příspěvek v poradenském fóru."
                    if str(settings["mode"] or "private") == "forum"
                    else "si zvolíš veřejný příspěvek, nebo soukromý kanál."
                    if str(settings["mode"] or "private") == "choice"
                    else "vytvoříme soukromý kanál pro tebe a naše poradce."
                )
            ),
            inline=False,
        )
        if str(settings["mode"] or "private") == "forum":
            embed.add_field(
                name="👁️ Veřejný režim",
                value="Požadavek a odpovědi uvidí všichni členové s přístupem do fóra.",
                inline=False,
            )
        elif str(settings["mode"] or "private") == "private":
            embed.add_field(
                name="🔒 Soukromý režim",
                value=(
                    "Požadavek uvidíš pouze ty, naši PC poradci a správci serveru. "
                    "Ostatní členové k vytvořenému kanálu nebudou mít přístup."
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name="🔒 Soukromá PC poradna",
                value=(
                    "Bot vytvoří samostatný kanál, který uvidíš pouze ty, "
                    "PC poradci a správci serveru. Hodí se, pokud nechceš "
                    "svůj požadavek řešit veřejně."
                ),
                inline=False,
            )
            embed.add_field(
                name="👁️ Veřejná PC poradna",
                value=(
                    "Bot vytvoří příspěvek ve fóru, který uvidí členové "
                    "s přístupem do poradny. Komunita tak může sledovat řešení "
                    "a případně také pomoct. Nevkládej sem osobní údaje."
                ),
                inline=False,
            )
        embed.set_footer(text=EMBED_FOOTER)
        await channel.send(embed=embed, view=AdvicePanel(self))
        await interaction.followup.send(
            f"✅ Panel byl odeslán do {channel.mention}.", ephemeral=True
        )

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        original = getattr(error, "original", error)
        message = "❌ Potřebuješ oprávnění **Administrátor**." if isinstance(
            original, app_commands.MissingPermissions
        ) else f"❌ Příkaz PC poradny selhal: {original}"
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PCAdvice(bot))
