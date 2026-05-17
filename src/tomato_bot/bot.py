from __future__ import annotations

__all__ = ("TomatoBot",)

import asyncio
from logging import getLogger
from typing import Final

import discord

from tomato_bot.application import ApplicationServices
from tomato_bot.repository import Repository, SQLiteRepository
from tomato_bot.ui.command import register_global_commands

logger: Final = getLogger(__name__)


class TomatoCommandTree(discord.app_commands.CommandTree["TomatoBot"]):
    async def interaction_check(
        self, interaction: discord.Interaction[TomatoBot], /
    ) -> bool:
        # トマトBotのサービスが提供できるようになっていない場合、
        # コマンドの実行はさせない。

        if not interaction.client.is_service_ready():
            await interaction.response.send_message(
                "現在、起動中です。10秒ほど待ってから再度試してください。",
                ephemeral=True,
            )
            return False

        return True


def intents() -> discord.Intents:
    intents = discord.Intents.none()
    intents.voice_states = True
    intents.guilds = True
    intents.messages = True
    return intents


ALLOWED_MENTIONS: Final = discord.AllowedMentions.none()


class TomatoBot(discord.Client):
    """このBotサービスのサブシステム群を配線するクラス"""

    def __init__(
        self, *, database_url: str, sync_global_commands_first: bool = False
    ) -> None:
        super().__init__(intents=intents(), allowed_mentions=ALLOWED_MENTIONS)

        self._service_ready = asyncio.Event()
        self._already_connected = False

        self.repository: Repository = SQLiteRepository()
        self.application_services = ApplicationServices(self)
        self.tree = TomatoCommandTree(self)

        self._database_url = database_url
        self._sync_global_commands_first = sync_global_commands_first

    async def setup_hook(self) -> None:
        # データベースの準備
        await self.repository.connect(self._database_url)

        # コマンドのセットアップ
        register_global_commands(self)

        # コマンドの登録
        if self._sync_global_commands_first:
            await self.tree.sync()
            logger.info("グローバルにアプリコマンドの同期を行いました。")

    def is_service_ready(self) -> bool:
        """このBotがユーザーにサービスを提供できる準備ができたかどうか。"""
        return self._service_ready.is_set()

    async def on_ready(self) -> None:
        self._service_ready.clear()
        await self.application_services.guild_initializer.ensure_joined_guilds_initialized()
        self._service_ready.set()

        if not self._already_connected:
            self._already_connected = True
            logger.info("接続しました。")

    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self.application_services.guild_initializer.on_guild_join(guild)

    async def on_raw_message_delete(
        self, payload: discord.RawMessageDeleteEvent
    ) -> None:
        """開始フロー用メッセージが消された場合は、残った開始状態を解放する。"""
        if payload.guild_id is None:
            return

        await (
            self.application_services.command_use_case.cancel_start_by_deleted_message(
                payload.guild_id,
                channel_id=payload.channel_id,
                message_id=payload.message_id,
            )
        )

    async def close(self) -> None:
        logger.info("終了中...")
        await self.application_services.sessions.teardown()
        await self.repository.close()
        return await super().close()
