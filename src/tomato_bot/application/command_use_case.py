from __future__ import annotations

__all__ = ("CommandUseCase", "CommandUseCaseException", "AlreadyStarting")

import discord

from tomato_bot.application.session_manager import SessionManager
from tomato_bot.domain import Routine
from tomato_bot.path_resolver import resolve_alarm_sound
from tomato_bot.repository import Repository


class CommandUseCaseException(Exception):
    """Botコマンドのエラー"""


class AlreadyStarting(CommandUseCaseException):
    """既に開始操作が始まっている時のエラー"""


class AlreadyStarted(CommandUseCaseException):
    """既に開始されている時のエラー"""


class CommandUseCase:
    """Botコマンドのユースケース"""

    def __init__(self, *, repository: Repository, sessions: SessionManager) -> None:
        self._repository = repository
        self._sessions = sessions
        self._starting = set[int]()

    async def begin_start_flow(self, guild_id: int, user_id: int) -> list[Routine]:
        """開始操作を初めて、ユーザーが利用可能なルーチンを取得する。"""
        if guild_id in self._starting:
            raise AlreadyStarting
        if self._sessions.is_created(guild_id):
            raise AlreadyStarted
        self._starting.add(guild_id)

        return await self._repository.get_available_routines(guild_id, user_id)

    async def prepare_start(
        self,
        routine: Routine,
        *,
        text_channel: discord.abc.Messageable,
        voice_channel: discord.VoiceChannel | discord.StageChannel,
    ) -> None:
        """接続しいつでもタイマーを動かせる状態にする。"""
        alarm_sound_file = await self._repository.get_alarm_sound_file(
            routine.alarm_sound_id
        )
        alarm_sound_path = resolve_alarm_sound(alarm_sound_file)

        await self._sessions.connect(
            routine,
            text_channel=text_channel,
            voice_channel=voice_channel,
            alarm_sound_path=alarm_sound_path,
        )

    def start(self, guild_id: int) -> None:
        """タイマーを開始する。"""
        self._sessions.start(guild_id)
        self._starting.discard(guild_id)

    async def cancel_start(self, guild_id: int) -> None:
        """開始操作をキャンセルする。"""
        await self._sessions.stop(guild_id)
        self._starting.discard(guild_id)

    async def stop(self, guild_id: int, *, force: bool = False) -> None:
        """ポモドーロタイマーを終了する。"""
        await self._sessions.stop(guild_id, force=force)
        self._starting.discard(guild_id)

    def pause(self, guild_id: int) -> None:
        """ポモドーロタイマーを一時停止する。"""
        self._sessions.pause(guild_id)

    def resume(self, guild_id: int) -> None:
        """ポモドーロタイマーを再開する。"""
        self._sessions.resume(guild_id)
