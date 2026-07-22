from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from typing import Iterable, Optional

import discord
from discord.ext import commands

from config import EMBED_COLOR, EMBED_FOOTER
from utils.database import db
from utils.logger import logger


class GiveawayService:
    """Databáze, plánování a ukončování giveaway."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tasks: dict[int, asyncio.Task] = {}

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def parse_datetime(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def create_giveaway(
        self,
        *,
        guild_id: int,
        channel_id: int,
        host_id: int,
        prize: str,
        description: str,
        winner_count: int,
        end_at: datetime,
    ) -> int:
        with db.connect() as conn:
            params = (
                guild_id,
                channel_id,
                host_id,
                prize,
                description,
                winner_count,
                end_at.astimezone(timezone.utc).isoformat(),
                db.now(),
            )

            if db.using_postgres:
                row = conn.execute("""
                    INSERT INTO giveaways (
                        guild_id, channel_id, host_id, prize, description,
                        winner_count, end_at, status, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)
                    RETURNING id
                """, params).fetchone()
                conn.commit()
                return int(row["id"])

            cursor = conn.execute("""
                INSERT INTO giveaways (
                    guild_id, channel_id, host_id, prize, description,
                    winner_count, end_at, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)
            """, params)
            conn.commit()
            return int(cursor.lastrowid)

    def set_message_id(self, giveaway_id: int, message_id: int) -> None:
        with db.connect() as conn:
            conn.execute(
                "UPDATE giveaways SET message_id = ? WHERE id = ?",
                (message_id, giveaway_id),
            )
            conn.commit()

    def get_giveaway(self, giveaway_id: int):
        with db.connect() as conn:
            return conn.execute(
                "SELECT * FROM giveaways WHERE id = ?",
                (giveaway_id,),
            ).fetchone()

    def get_active_giveaways(self):
        with db.connect() as conn:
            return conn.execute("""
                SELECT * FROM giveaways
                WHERE status = 'active'
                ORDER BY end_at ASC
            """).fetchall()

    def get_guild_giveaways(self, guild_id: int, *, active_only: bool = False):
        with db.connect() as conn:
            if active_only:
                return conn.execute("""
                    SELECT * FROM giveaways
                    WHERE guild_id = ? AND status = 'active'
                    ORDER BY end_at ASC
                """, (guild_id,)).fetchall()

            return conn.execute("""
                SELECT * FROM giveaways
                WHERE guild_id = ?
                ORDER BY id DESC
                LIMIT 25
            """, (guild_id,)).fetchall()

    def add_entry(self, giveaway_id: int, user_id: int) -> bool:
        with db.connect() as conn:
            try:
                if db.using_postgres:
                    cursor = conn.execute("""
                        INSERT INTO giveaway_entries
                        (giveaway_id, user_id, joined_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT (giveaway_id, user_id) DO NOTHING
                    """, (giveaway_id, user_id, db.now()))
                else:
                    cursor = conn.execute("""
                        INSERT OR IGNORE INTO giveaway_entries
                        (giveaway_id, user_id, joined_at)
                        VALUES (?, ?, ?)
                    """, (giveaway_id, user_id, db.now()))
                conn.commit()
                return cursor.rowcount > 0
            except Exception:
                logger.exception("Nepodařilo se přidat účastníka do giveaway %s.", giveaway_id)
                raise

    def remove_entry(self, giveaway_id: int, user_id: int) -> bool:
        with db.connect() as conn:
            cursor = conn.execute("""
                DELETE FROM giveaway_entries
                WHERE giveaway_id = ? AND user_id = ?
            """, (giveaway_id, user_id))
            conn.commit()
            return cursor.rowcount > 0

    def count_entries(self, giveaway_id: int) -> int:
        with db.connect() as conn:
            row = conn.execute("""
                SELECT COUNT(*) AS c
                FROM giveaway_entries
                WHERE giveaway_id = ?
            """, (giveaway_id,)).fetchone()
            return int(row["c"])

    def get_entry_ids(self, giveaway_id: int) -> list[int]:
        with db.connect() as conn:
            rows = conn.execute("""
                SELECT user_id
                FROM giveaway_entries
                WHERE giveaway_id = ?
            """, (giveaway_id,)).fetchall()
            return [int(row["user_id"]) for row in rows]

    def mark_ended(self, giveaway_id: int, winner_ids: Iterable[int]) -> None:
        winner_text = ",".join(str(user_id) for user_id in winner_ids)
        with db.connect() as conn:
            conn.execute("""
                UPDATE giveaways
                SET status = 'ended', ended_at = ?, winners_text = ?
                WHERE id = ?
            """, (db.now(), winner_text, giveaway_id))
            conn.commit()

    def mark_deleted(self, giveaway_id: int) -> None:
        with db.connect() as conn:
            conn.execute("""
                UPDATE giveaways
                SET status = 'deleted', ended_at = ?
                WHERE id = ?
            """, (db.now(), giveaway_id))
            conn.commit()

    def build_embed(self, giveaway, *, ended: bool = False) -> discord.Embed:
        giveaway_id = int(giveaway["id"])
        end_at = self.parse_datetime(giveaway["end_at"])
        participants = self.count_entries(giveaway_id)

        embed = discord.Embed(
            title=f"🎁 {giveaway['prize']}",
            description=giveaway["description"],
            color=EMBED_COLOR,
        )
        embed.add_field(
            name="🏆 Počet výherců",
            value=str(giveaway["winner_count"]),
            inline=True,
        )
        embed.add_field(
            name="👥 Účastníků",
            value=str(participants),
            inline=True,
        )
        embed.add_field(
            name="🎙️ Pořadatel",
            value=f"<@{giveaway['host_id']}>",
            inline=True,
        )

        if ended:
            winners_text = giveaway["winners_text"] or ""
            winner_ids = [item for item in winners_text.split(",") if item]
            winners = ", ".join(f"<@{item}>" for item in winner_ids)
            embed.add_field(
                name="✅ Giveaway skončila",
                value=winners or "Nebyl vybrán žádný výherce.",
                inline=False,
            )
        else:
            embed.add_field(
                name="⏰ Končí",
                value=(
                    f"{discord.utils.format_dt(end_at, style='F')}\n"
                    f"({discord.utils.format_dt(end_at, style='R')})"
                ),
                inline=False,
            )
            embed.add_field(
                name="Jak se zapojit?",
                value="Klikni na tlačítko **🎉 Zúčastnit se** níže.",
                inline=False,
            )

        embed.set_footer(text=f"{EMBED_FOOTER} • Giveaway ID: {giveaway_id}")
        return embed

    async def update_message(self, giveaway_id: int, *, ended: bool = False) -> None:
        giveaway = self.get_giveaway(giveaway_id)
        if giveaway is None or not giveaway["message_id"]:
            return

        channel = self.bot.get_channel(int(giveaway["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            try:
                fetched = await self.bot.fetch_channel(int(giveaway["channel_id"]))
                channel = fetched if isinstance(fetched, discord.TextChannel) else None
            except discord.HTTPException:
                channel = None

        if channel is None:
            logger.warning("Giveaway kanál %s nebyl nalezen.", giveaway["channel_id"])
            return

        try:
            message = await channel.fetch_message(int(giveaway["message_id"]))
            view = None
            if not ended:
                from ui.giveaway_views import GiveawayJoinView
                view = GiveawayJoinView(self, giveaway_id)
            await message.edit(embed=self.build_embed(giveaway, ended=ended), view=view)
        except discord.NotFound:
            logger.warning("Giveaway zpráva %s nebyla nalezena.", giveaway["message_id"])
        except discord.HTTPException:
            logger.exception("Nepodařilo se upravit giveaway zprávu %s.", giveaway["message_id"])

    def choose_winners(self, giveaway_id: int, winner_count: int) -> list[int]:
        entry_ids = self.get_entry_ids(giveaway_id)
        if not entry_ids:
            return []
        return random.sample(entry_ids, k=min(winner_count, len(entry_ids)))

    async def end_giveaway(self, giveaway_id: int, *, announce: bool = True) -> list[int]:
        giveaway = self.get_giveaway(giveaway_id)
        if giveaway is None or giveaway["status"] != "active":
            return []

        winner_ids = self.choose_winners(giveaway_id, int(giveaway["winner_count"]))
        self.mark_ended(giveaway_id, winner_ids)
        await self.update_message(giveaway_id, ended=True)

        if announce:
            channel = self.bot.get_channel(int(giveaway["channel_id"]))
            if isinstance(channel, discord.TextChannel):
                if winner_ids:
                    mentions = ", ".join(f"<@{user_id}>" for user_id in winner_ids)
                    text = f"🎉 Giveaway **{giveaway['prize']}** skončila! Výherci: {mentions}"
                else:
                    text = f"🎁 Giveaway **{giveaway['prize']}** skončila bez účastníků."

                try:
                    await channel.send(text)
                except discord.HTTPException:
                    logger.exception("Nepodařilo se oznámit výherce giveaway %s.", giveaway_id)

        for user_id in winner_ids:
            try:
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                await user.send(
                    f"🎉 Vyhrál/a jsi giveaway **{giveaway['prize']}** "
                    f"na serveru **{self.bot.get_guild(int(giveaway['guild_id'])).name if self.bot.get_guild(int(giveaway['guild_id'])) else 'Discord'}**."
                )
            except discord.HTTPException:
                pass

        task = self.tasks.pop(giveaway_id, None)
        if task and task is not asyncio.current_task():
            task.cancel()

        logger.info("Giveaway %s byla ukončena. Výherci: %s", giveaway_id, winner_ids)
        return winner_ids

    async def reroll(self, giveaway_id: int, count: int = 1) -> list[int]:
        giveaway = self.get_giveaway(giveaway_id)
        if giveaway is None or giveaway["status"] != "ended":
            return []
        return self.choose_winners(giveaway_id, count)

    async def _wait_and_end(self, giveaway_id: int, end_at: datetime) -> None:
        try:
            delay = max(0.0, (end_at - self.now()).total_seconds())
            await asyncio.sleep(delay)
            await self.end_giveaway(giveaway_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Automatické ukončení giveaway %s selhalo.", giveaway_id)

    def schedule(self, giveaway_id: int, end_at: datetime) -> None:
        previous = self.tasks.pop(giveaway_id, None)
        if previous:
            previous.cancel()
        self.tasks[giveaway_id] = asyncio.create_task(
            self._wait_and_end(giveaway_id, end_at),
            name=f"giveaway-{giveaway_id}",
        )

    async def restore_active(self) -> None:
        await self.bot.wait_until_ready()
        active = self.get_active_giveaways()
        for giveaway in active:
            giveaway_id = int(giveaway["id"])
            end_at = self.parse_datetime(giveaway["end_at"])
            if end_at <= self.now():
                await self.end_giveaway(giveaway_id)
            else:
                self.schedule(giveaway_id, end_at)
        logger.info("Obnoveno %s aktivních giveaway.", len(active))

    def cancel_all(self) -> None:
        for task in self.tasks.values():
            task.cancel()
        self.tasks.clear()
