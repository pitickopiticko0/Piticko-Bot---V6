"""Ručně ověřované ranky Arena Breakout: Infinite."""

import discord
from discord import app_commands
from discord.ext import commands

from utils.database import db
from utils.logger import logger


RANKS = {
    "rookie": "Rookie",
    "vanguard": "Vanguard",
    "elite": "Elite",
    "expert": "Expert",
    "master": "Master",
    "ace": "Ace",
    "hero": "Hero",
    "legend": "Legend",
}
RANK_CHOICES = [
    app_commands.Choice(name=name, value=key) for key, name in RANKS.items()
]
RANK_RADIO_OPTIONS = [
    discord.RadioGroupOption(label=name, value=key) for key, name in RANKS.items()
]


class RankRequestModal(discord.ui.Modal, title="Ověření ABI ranku"):
    game_name = discord.ui.Label(
        text="Herní jméno",
        component=discord.ui.TextInput(
            placeholder="Přesné jméno ve hře",
            min_length=2,
            max_length=32,
        ),
    )
    uid = discord.ui.Label(
        text="UID / GID",
        component=discord.ui.TextInput(
            placeholder="Tvoje Arena Breakout: Infinite UID/GID",
            min_length=3,
            max_length=64,
        ),
    )
    rank = discord.ui.Label(
        text="Aktuální hodnost",
        component=discord.ui.RadioGroup(options=RANK_RADIO_OPTIONS),
    )
    division = discord.ui.Label(
        text="Divize (volitelné)",
        description="Například I, II, III, IV nebo V.",
        component=discord.ui.TextInput(
            placeholder="Např. III",
            required=False,
            max_length=16,
        ),
    )
    screenshot = discord.ui.Label(
        text="Screenshot profilu",
        description="Nahraj celý a čitelný obrázek s UID i rankem (max. 8 MB).",
        component=discord.ui.FileUpload(min_values=1, max_values=1),
    )

    def __init__(self, cog: "ABIRank"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        division = str(self.division.component.value).strip() or None
        await self.cog.submit_request(
            interaction,
            game_name=str(self.game_name.component.value).strip(),
            uid=str(self.uid.component.value).strip(),
            rank_key=str(self.rank.component.value),
            screenshot=self.screenshot.component.values[0],
            division=division,
        )


class RankRequestPanel(discord.ui.View):
    def __init__(self, cog: "ABIRank"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Požádat o ověření",
        emoji="🎖️",
        style=discord.ButtonStyle.primary,
        custom_id="piticko:abi_rank:request",
    )
    async def request_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Panel funguje pouze na serveru.", ephemeral=True
            )
            return
        settings = db.get_abi_rank_settings(interaction.guild.id)
        if settings is None or not settings["enabled"]:
            await interaction.response.send_message(
                "❌ ABI Rank není na tomto serveru nastavený.", ephemeral=True
            )
            return
        if db.get_pending_abi_rank(interaction.guild.id, interaction.user.id):
            await interaction.response.send_message(
                "❌ Už máš jednu žádost čekající na kontrolu.", ephemeral=True
            )
            return
        await interaction.response.send_modal(RankRequestModal(self.cog))


class RejectModal(discord.ui.Modal, title="Zamítnutí ABI ranku"):
    reason = discord.ui.TextInput(
        label="Důvod", style=discord.TextStyle.paragraph,
        min_length=3, max_length=500,
        placeholder="Např. screenshot neobsahuje UID nebo rank.",
    )

    def __init__(self, cog: "ABIRank"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.reject(interaction, str(self.reason).strip())


class ReviewControls(discord.ui.View):
    def __init__(self, cog: "ABIRank"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Schválit", emoji="✅", style=discord.ButtonStyle.success,
        custom_id="piticko:abi_rank:approve",
    )
    async def approve_button(self, interaction: discord.Interaction,
                             button: discord.ui.Button):
        await self.cog.approve(interaction)

    @discord.ui.button(
        label="Zamítnout", emoji="❌", style=discord.ButtonStyle.danger,
        custom_id="piticko:abi_rank:reject",
    )
    async def reject_button(self, interaction: discord.Interaction,
                            button: discord.ui.Button):
        if not self.cog.can_review(interaction):
            await interaction.response.send_message(
                "❌ Tuto žádost může vyřídit pouze ABI ověřovatel.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(RejectModal(self.cog))


class ABIRank(commands.GroupCog, group_name="abirank"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(ReviewControls(self))
        self.bot.add_view(RankRequestPanel(self))

    def can_review(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return False
        settings = db.get_abi_rank_settings(interaction.guild.id)
        if settings is None:
            return False
        return (
            interaction.user.guild_permissions.administrator
            or any(
                role.id == int(settings["reviewer_role_id"])
                for role in interaction.user.roles
            )
        )

    def request_from_interaction(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.message is None:
            return None
        return db.get_abi_rank_by_review_message(
            interaction.guild.id, interaction.message.id
        )

    @app_commands.command(
        name="zadost", description="Požádej o ověření svého ABI ranku."
    )
    @app_commands.describe(
        herni_jmeno="Přesné jméno ve hře",
        uid="Tvoje ABI UID/GID",
        rank="Aktuální hodnost",
        screenshot="Celý a čitelný screenshot herního profilu",
        divize="Volitelně např. I, II, III, IV nebo V",
    )
    @app_commands.choices(rank=RANK_CHOICES)
    async def request(
        self,
        interaction: discord.Interaction,
        herni_jmeno: app_commands.Range[str, 2, 32],
        uid: app_commands.Range[str, 3, 64],
        rank: app_commands.Choice[str],
        screenshot: discord.Attachment,
        divize: app_commands.Range[str, 1, 16] | None = None,
    ) -> None:
        await self.submit_request(
            interaction,
            game_name=str(herni_jmeno).strip(),
            uid=str(uid).strip(),
            rank_key=rank.value,
            screenshot=screenshot,
            division=str(divize).strip() if divize else None,
        )

    async def submit_request(
        self,
        interaction: discord.Interaction,
        *,
        game_name: str,
        uid: str,
        rank_key: str,
        screenshot: discord.Attachment,
        division: str | None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Příkaz funguje pouze na serveru.", ephemeral=True
            )
            return
        settings = db.get_abi_rank_settings(interaction.guild.id)
        if settings is None or not settings["enabled"]:
            await interaction.response.send_message(
                "❌ ABI Rank není na tomto serveru nastavený.", ephemeral=True
            )
            return
        if db.get_pending_abi_rank(interaction.guild.id, interaction.user.id):
            await interaction.response.send_message(
                "❌ Už máš jednu žádost čekající na kontrolu.", ephemeral=True
            )
            return
        if rank_key not in RANKS:
            await interaction.response.send_message(
                "❌ Vybraný ABI rank není platný.", ephemeral=True
            )
            return
        content_type = (screenshot.content_type or "").lower()
        if not content_type.startswith("image/"):
            await interaction.response.send_message(
                "❌ Důkaz musí být obrázek (PNG, JPG nebo WebP).", ephemeral=True
            )
            return
        if screenshot.size > 8 * 1024 * 1024:
            await interaction.response.send_message(
                "❌ Screenshot může mít nejvýše 8 MB.", ephemeral=True
            )
            return
        channel = interaction.guild.get_channel(int(settings["review_channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ Nastavený kontrolní kanál neexistuje.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        request_id = db.create_abi_rank_request(
            interaction.guild.id, interaction.user.id, game_name,
            uid, rank_key,
            division.upper() if division else None, screenshot.url,
        )
        rank_name = RANKS[rank_key] + (f" {division.upper()}" if division else "")
        embed = discord.Embed(
            title=f"ABI Rank žádost #{request_id}",
            description=f"Žadatel: {interaction.user.mention}",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Herní jméno", value=game_name, inline=True)
        embed.add_field(name="UID/GID", value=uid, inline=True)
        embed.add_field(name="Požadovaný rank", value=rank_name, inline=True)
        embed.set_image(url=screenshot.url)
        embed.set_footer(text="Údaje ověř ručně podle screenshotu.")
        try:
            message = await channel.send(
                content=f"<@&{settings['reviewer_role_id']}>",
                embed=embed, view=ReviewControls(self),
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
        except discord.HTTPException:
            db.finish_abi_rank_request(
                request_id, "failed", self.bot.user.id if self.bot.user else 0,
                "Kontrolní zprávu se nepodařilo odeslat.",
            )
            logger.exception("Nelze odeslat ABI Rank žádost %s.", request_id)
            await interaction.followup.send(
                "❌ Žádost se nepodařilo odeslat ke kontrole.", ephemeral=True
            )
            return
        db.set_abi_rank_review_message(request_id, message.id)
        await interaction.followup.send(
            f"✅ Žádost #{request_id} byla odeslána ke kontrole.", ephemeral=True
        )

    @app_commands.command(
        name="panel", description="Odešle panel pro žádosti o ověření ABI ranku."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.bot_has_permissions(send_messages=True, embed_links=True)
    async def panel(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Příkaz funguje pouze na serveru.", ephemeral=True
            )
            return
        settings = db.get_abi_rank_settings(interaction.guild.id)
        if settings is None or not settings["enabled"]:
            await interaction.response.send_message(
                "❌ Nejprve zapni a nastav ABI Rank ve webovém dashboardu.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🎖️ Ověření Arena Breakout: Infinite ranku",
            description=(
                "Klikni na tlačítko níže a odešli svůj aktuální rank ke kontrole. "
                "Ověřovatel žádost ručně porovná se screenshotem."
            ),
            color=discord.Color.orange(),
        )
        embed.add_field(
            name="Co budeš potřebovat",
            value=(
                "• herní jméno a UID/GID\n"
                "• aktuální rank a případně divizi\n"
                "• celý a čitelný screenshot profilu"
            ),
            inline=False,
        )
        embed.add_field(
            name="Pravidla",
            value=(
                "Můžeš mít pouze jednu nevyřízenou žádost. Falešné nebo "
                "nečitelné důkazy budou zamítnuty."
            ),
            inline=False,
        )
        embed.set_footer(text="Piticko Bot • Ruční ověření ABI ranku")
        await interaction.response.defer(ephemeral=True)
        await interaction.channel.send(embed=embed, view=RankRequestPanel(self))
        await interaction.followup.send(
            "✅ ABI Rank panel byl odeslán do tohoto kanálu.", ephemeral=True
        )

    async def approve(self, interaction: discord.Interaction) -> None:
        if not self.can_review(interaction):
            await interaction.response.send_message(
                "❌ Tuto žádost může vyřídit pouze ABI ověřovatel.", ephemeral=True
            )
            return
        request = self.request_from_interaction(interaction)
        if request is None or request["status"] != "pending":
            await interaction.response.send_message(
                "❌ Žádost už byla vyřízena nebo chybí.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = guild.get_member(int(request["user_id"]))
        settings = db.get_abi_rank_settings(guild.id)
        role_id = settings[f"{request['rank_key']}_role_id"]
        if member is None:
            await interaction.followup.send(
                "❌ Žadatel už není členem serveru.", ephemeral=True
            )
            return
        new_role = guild.get_role(int(role_id)) if role_id else None
        configured_ids = {
            int(settings[f"{key}_role_id"])
            for key in RANKS if settings[f"{key}_role_id"]
        }
        updated_roles = [
            role for role in member.roles
            if role.id not in configured_ids and role != guild.default_role
        ]
        if new_role:
            updated_roles.append(new_role)
        try:
            await member.edit(
                roles=updated_roles, reason="Změna ověřeného ABI ranku"
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Bot nemůže upravit rank roli. Přesuň jeho roli výše.",
                ephemeral=True,
            )
            return
        db.finish_abi_rank_request(request["id"], "approved", interaction.user.id)
        await self.finish_message(interaction, request, "Schváleno", discord.Color.green())
        try:
            await member.send(
                f"✅ Tvůj ABI rank **{RANKS[request['rank_key']]}** na serveru "
                f"**{guild.name}** byl schválen."
            )
        except discord.HTTPException:
            pass
        role_note = new_role.mention if new_role else "bez nastavené Discord role"
        await interaction.followup.send(
            f"✅ Rank schválen — {role_note}.", ephemeral=True
        )

    async def reject(self, interaction: discord.Interaction, reason: str) -> None:
        if not self.can_review(interaction):
            await interaction.response.send_message("❌ Nemáš oprávnění.", ephemeral=True)
            return
        request = self.request_from_interaction(interaction)
        if request is None or request["status"] != "pending":
            await interaction.response.send_message(
                "❌ Žádost už byla vyřízena nebo chybí.", ephemeral=True
            )
            return
        db.finish_abi_rank_request(
            request["id"], "rejected", interaction.user.id, reason
        )
        await self.finish_message(
            interaction, request, f"Zamítnuto: {reason}", discord.Color.red()
        )
        member = interaction.guild.get_member(int(request["user_id"]))
        if member:
            try:
                await member.send(
                    f"❌ Tvoje ABI Rank žádost na serveru **{interaction.guild.name}** "
                    f"byla zamítnuta.\nDůvod: {reason}"
                )
            except discord.HTTPException:
                pass
        await interaction.response.send_message("✅ Žádost zamítnuta.", ephemeral=True)

    @staticmethod
    async def finish_message(interaction: discord.Interaction, request,
                             result: str, color: discord.Color) -> None:
        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        embed.color = color
        embed.add_field(
            name="Výsledek",
            value=f"{result}\nOvěřil: {interaction.user.mention}",
            inline=False,
        )
        await interaction.message.edit(embed=embed, view=None)

    @app_commands.command(
        name="zebricek", description="Zobrazí ověřené ABI ranky členů serveru."
    )
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Příkaz funguje pouze na serveru.", ephemeral=True
            )
            return
        rows = db.get_abi_rank_leaderboard(interaction.guild.id, 20)
        if not rows:
            await interaction.response.send_message(
                "Zatím tu nejsou žádné schválené ABI ranky."
            )
            return
        lines = [
            f"**{index}.** <@{row['user_id']}> — "
            f"**{RANKS.get(row['rank_key'], row['rank_key'])}"
            f"{' ' + row['division'] if row['division'] else ''}** "
            f"(`{row['game_name']}`)"
            for index, row in enumerate(rows, 1)
        ]
        embed = discord.Embed(
            title="🏆 Arena Breakout: Infinite — serverový žebříček",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        embed.set_footer(text="Ranky jsou ručně ověřené podle dodaných screenshotů.")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ABIRank(bot))
