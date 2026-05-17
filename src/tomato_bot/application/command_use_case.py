from __future__ import annotations

__all__ = (
    "CommandUseCase",
    "CommandUseCaseException",
    "AlreadyStarting",
    "AlreadyStarted",
    "NoStartFlow",
    "StartFlow",
    "StartFlowMessageRef",
)

import contextlib
from collections.abc import Mapping
from dataclasses import dataclass, field

import discord

from tomato_bot.application.session_manager import SessionManager, SessionNotFound
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
class StartFlowMessageRef:
    """開始フローを表示しているDiscordメッセージの参照"""

    channel_id: int
    message_id: int


@dataclass(frozen=True, kw_only=True)
class StartFlow:
    """開始フローの状態"""

    guild_id: int
    routines: Mapping[int, Routine] = field(default_factory=dict)
    start_prompt_jump_url: str | None = None
    message_refs: frozenset[StartFlowMessageRef] = frozenset()


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
        return self._replace_start_flow(guild_id, start_prompt_jump_url=jump_url)

    def attach_start_flow_message(
        self,
        guild_id: int,
        *,
        channel_id: int,
        message_id: int,
        jump_url: str | None = None,
    ) -> StartFlow:
        """開始フローに使っているDiscordメッセージを追跡対象に追加する。"""
        if guild_id not in self._start_flows:
            raise NoStartFlow

        old_flow = self._start_flows[guild_id]
        message_refs = old_flow.message_refs | frozenset(
            (StartFlowMessageRef(channel_id=channel_id, message_id=message_id),)
        )

        return self._replace_start_flow(
            guild_id,
            start_prompt_jump_url=jump_url or old_flow.start_prompt_jump_url,
            message_refs=message_refs,
        )

    def _replace_start_flow(
        self,
        guild_id: int,
        *,
        start_prompt_jump_url: str | None,
        message_refs: frozenset[StartFlowMessageRef] | None = None,
    ) -> StartFlow:
        """既存の開始フロー状態を一部だけ差し替える。"""
        if guild_id not in self._start_flows:
            raise NoStartFlow

        old_flow = self._start_flows[guild_id]
        flow = StartFlow(
            guild_id=old_flow.guild_id,
            routines=old_flow.routines,
            start_prompt_jump_url=start_prompt_jump_url,
            message_refs=old_flow.message_refs
            if message_refs is None
            else message_refs,
        )
        self._start_flows[guild_id] = flow

        return flow

    async def cancel_start_by_deleted_message(
        self,
        guild_id: int,
        *,
        channel_id: int,
        message_id: int,
    ) -> bool:
        """追跡中の開始フローメッセージが消された場合に開始操作をキャンセルする。"""
        flow = self._start_flows.get(guild_id)
        if flow is None:
            return False

        message_ref = StartFlowMessageRef(channel_id=channel_id, message_id=message_id)
        if message_ref not in flow.message_refs:
            return False

        await self.cancel_start(guild_id)
        return True

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
        flow = self._start_flows.pop(guild_id, None)
        if flow is None:
            return

        with contextlib.suppress(SessionNotFound):
            await self._sessions.stop(guild_id)

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
