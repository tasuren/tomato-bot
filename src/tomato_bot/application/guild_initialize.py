from __future__ import annotations

__all__ = ("GuildInitializeService",)

from collections.abc import Collection
from typing import TYPE_CHECKING

import discord

from tomato_bot.default_settings import DEFAULT_ROUTINES
from tomato_bot.repository import NewRoutineRecord

if TYPE_CHECKING:
    from tomato_bot.bot import TomatoBot


class GuildInitializeService:
    """起動時やサーバーへのBot導入時に、サーバーの初期設定を済ませるサービス

    これをしなければ、ルーチンのデフォルト設定が反映されない。
    """

    def __init__(self, bot: TomatoBot) -> None:
        self._bot = bot

    async def _ensure_guilds_initialized(self, guild_ids: Collection[int]) -> None:
        repository = self._bot.repository

        async with repository.transaction():
            await repository.insert_guild_settings_if_missing(guild_ids)
            uninitialized = await repository.get_uninitialized_guild_ids(guild_ids)

            if uninitialized:
                routines = (
                    NewRoutineRecord(
                        name=routine.name,
                        description=routine.description,
                        guild_id=guild_id,
                        user_id=None,
                        alarm_sound_id=routine.alarm_sound_id,
                        phases=routine.phases,
                    )
                    for guild_id in uninitialized
                    for routine in DEFAULT_ROUTINES
                )

                await repository.insert_routines(routines)
                await repository.mark_guilds_initialized(uninitialized)

    async def ensure_joined_guilds_initialized(self) -> None:
        """Botが参加しているサーバー群が既に設定済みであることを保証する。"""
        if not self._bot.is_ready():
            raise RuntimeError(
                "Botがまだ準備完了していないため、サーバーの初期設定保証処理が開始できません。"
            )

        guild_ids = tuple(map(lambda g: g.id, self._bot.guilds))
        if guild_ids:
            await self._ensure_guilds_initialized(guild_ids)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Botがサーバーに参加した時に、サーバーを初期化する。"""
        await self._ensure_guilds_initialized((guild.id,))
