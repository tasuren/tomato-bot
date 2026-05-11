from __future__ import annotations

__all__ = (
    "CommandUseCase",
    "CommandUseCaseException",
    "AlreadyStarting",
    "AlreadyStarted",
    "NoStartFlow",
)

from collections.abc import Mapping
from dataclasses import dataclass, field

import discord

from tomato_bot.application.session_manager import SessionManager
from tomato_bot.domain import Routine
from tomato_bot.path_resolver import resolve_alarm_sound
from tomato_bot.repository import Repository


class CommandUseCaseException(Exception):
    """Botコマンドのエラー"""


@dataclass(frozen=True)
class AlreadyStarting(CommandUseCaseException):
    """既に開始操作が始まっている時のエラー"""

    start_prompt_jump_url: str | None = None


class AlreadyStarted(CommandUseCaseException):
    """既に開始されている時のエラー"""


class NoStartFlow(CommandUseCaseException):
    """指定されたサーバーの開始フロー状態がまだない時のエラー"""


@dataclass(frozen=True, kw_only=True)
class StartFlow:
    """開始フローの状態"""

    guild_id: int
    routines: Mapping[int, Routine] = field(default_factory=dict)
    start_prompt_jump_url: str | None = None


class CommandUseCase:
    """Botコマンドのユースケース"""

    def __init__(self, *, repository: Repository, sessions: SessionManager) -> None:
        self._repository = repository
        self._sessions = sessions
        self._start_flows = dict[int, StartFlow]()

    async def begin_start_flow(self, guild_id: int, user_id: int) -> StartFlow:
        """開始操作を初めて、ユーザーが利用可能なルーチンを取得する。"""
        if (flow := self._start_flows.get(guild_id)) is not None:
            raise AlreadyStarting(flow.start_prompt_jump_url)
        if self._sessions.is_created(guild_id):
            raise AlreadyStarted

        self._start_flows[guild_id] = StartFlow(guild_id=guild_id)

        try:
            routines = await self._repository.get_available_routines(guild_id, user_id)
        finally:
            self._start_flows.pop(guild_id, None)

        flow = StartFlow(guild_id=guild_id, routines={r.id: r for r in routines})

        self._start_flows[guild_id] = flow
        return flow

    def attach_start_prompt_jump_url(self, guild_id: int, jump_url: str) -> StartFlow:
        """開始操作を始めたきっかけのメッセージへのリンクを状態に保存しておく。"""
        if guild_id not in self._start_flows:
            raise NoStartFlow

        old_flow = self._start_flows[guild_id]
        flow = StartFlow(
            guild_id=old_flow.guild_id,
            routines=old_flow.routines,
            start_prompt_jump_url=jump_url,
        )
        self._start_flows[guild_id] = flow

        return flow

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
        try:
            self._sessions.start(guild_id)
        finally:
            self._start_flows.pop(guild_id, None)

    async def cancel_start(self, guild_id: int) -> None:
        """開始操作をキャンセルする。"""
        try:
            await self._sessions.stop(guild_id)
        finally:
            self._start_flows.pop(guild_id, None)

    async def stop(self, guild_id: int, *, force: bool = False) -> None:
        """ポモドーロタイマーを終了する。"""
        try:
            await self._sessions.stop(guild_id, force=force)
        finally:
            self._start_flows.pop(guild_id, None)

    def pause(self, guild_id: int) -> None:
        """ポモドーロタイマーを一時停止する。"""
        self._sessions.pause(guild_id)

    def resume(self, guild_id: int) -> None:
        """ポモドーロタイマーを再開する。"""
        self._sessions.resume(guild_id)
