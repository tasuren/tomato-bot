from __future__ import annotations

__all__ = (
    "SessionManager",
    "SessionException",
    "SessionNotFound",
    "SessionAlreadyCreated",
)

import asyncio
import contextlib
import math
from dataclasses import dataclass
from logging import getLogger
from pathlib import PurePath
from time import time
from typing import Final, Self

import discord

from tomato_bot.audio_source import WavAudio
from tomato_bot.domain import (
    Phase,
    PhaseChanged,
    PhasePaused,
    PhaseResumed,
    PhaseStarted,
    PomodoroTimer,
    Routine,
    TimerEvent,
)
from tomato_bot.utils import normalize_nested_quotes

logger: Final = getLogger(__name__)


class TimerSessionError(Exception):
    """``TimerSession``関連のエラー"""


class TimerAlreadyStarted(TimerSessionError):
    """既にポモドーロタイマーが動作している場合のエラー"""


class TimerAlreadyStopped(TimerSessionError):
    """既にポモドーロタイマーが停止している場合のエラー"""


@dataclass(frozen=True, kw_only=True)
class PhaseNotificationSnapshot:
    """フェーズ状況の通知に関する状態のスナップショット"""

    message: discord.Message
    ends_at: float
    kind: str


class TimerSession:
    """Discordとタイマーの橋渡しを行うadapter"""

    def __init__(
        self,
        routine: Routine,
        *,
        text_channel: discord.abc.Messageable,
        voice_client: discord.VoiceClient,
        alarm_sound_path: PurePath,
    ) -> None:
        self._timer = PomodoroTimer(routine)

        self._text_channel = text_channel
        self._voice_client = voice_client
        self._alarm_sound_path = alarm_sound_path

        self._has_phase_switched: bool = False
        self._last_notification: PhaseNotificationSnapshot | None = None
        self._task: asyncio.Task[None] | None = None

    async def _on_timer_event(self, event: TimerEvent) -> None:
        match event:
            case PhaseStarted(phase=phase, ends_at=ends_at):
                await self._on_phase_started(phase, ends_at)
            case PhaseChanged(phase=phase, ends_at=ends_at):
                await self._on_phase_changed(phase, ends_at)
            case PhasePaused(phase=phase, remaining=remaining):
                await self._on_phase_paused(phase, remaining)
            case PhaseResumed(phase=phase, new_ends_at=new_ends_at):
                await self._on_phase_resumed(phase, new_ends_at)

    async def _on_phase_started(self, phase: Phase, ends_at: float) -> None:
        # ポモドーロタイマーが動き出したことを通知する。
        kind = normalize_nested_quotes(phase.kind)
        content = format_phase_status(
            kind=kind, ends_at=ends_at, has_phase_switched=self._has_phase_switched
        )
        message = await self._text_channel.send(content)

        self._last_notification = PhaseNotificationSnapshot(
            message=message,
            kind=kind,
            ends_at=ends_at,
        )

    async def _on_phase_changed(self, phase: Phase, ends_at: float) -> None:
        # アラーム音を再生
        f = open(self._alarm_sound_path, "rb")
        self._voice_client.play(WavAudio(f), after=lambda _: f.close())

        # 邪魔なので前回の通知メッセージを削除
        if self._last_notification is not None:
            content = format_pinned_phase_status(
                self._last_notification.kind,
                self._last_notification.ends_at,
                self._has_phase_switched,
            )
            await self._last_notification.message.edit(content=content)

        self._has_phase_switched = True

        # 新しい通知メッセージを送信
        kind = normalize_nested_quotes(phase.kind)
        content = format_phase_status(
            kind=kind, ends_at=ends_at, has_phase_switched=self._has_phase_switched
        )
        message = await self._text_channel.send(content)

        self._last_notification = PhaseNotificationSnapshot(
            message=message, kind=kind, ends_at=ends_at
        )

    async def _on_phase_paused(self, phase: Phase, remaining: float) -> None:
        if self._last_notification is not None:
            content = format_pinned_phase_status(
                phase.kind,
                self._last_notification.ends_at,
                self._has_phase_switched,
            )
            await self._last_notification.message.edit(content=content)

    async def _on_phase_resumed(self, phase: Phase, new_ends_at: float) -> None:
        if self._last_notification is not None:
            content = format_phase_status(
                phase.kind,
                new_ends_at,
                self._has_phase_switched,
            )
            await self._last_notification.message.edit(content=content)

    async def _consume_events(self) -> None:
        while True:
            await self._on_timer_event(await self._timer.events.get())

    async def _timer_runner(self) -> None:
        try:
            await asyncio.gather(self._timer.run(), self._consume_events())
        except Exception:
            logger.exception("ポモドーロタイマーの処理中にエラーが発生しました。")

    @classmethod
    async def connect(
        cls,
        routine: Routine,
        *,
        text_channel: discord.abc.Messageable,
        voice_channel: discord.VoiceChannel | discord.StageChannel,
        alarm_sound_path: PurePath,
    ) -> Self:
        voice_client = await voice_channel.connect(self_deaf=True)
        return cls(
            routine,
            text_channel=text_channel,
            voice_client=voice_client,
            alarm_sound_path=alarm_sound_path,
        )

    async def disconnect(self, *, force: bool = False) -> None:
        """切断処理をする。"""
        await self._voice_client.disconnect(force=force)

    def start(self) -> None:
        """ポモドーロタイマーを動かす。"""
        if self._task is not None:
            raise TimerAlreadyStarted("既にポモドーロタイマーは動作しています。")

        self._task = asyncio.create_task(
            self._timer_runner(), name=f"TimerSession {self._voice_client.guild.id}"
        )

    async def stop(self) -> None:
        """ポモドーロタイマーを停止する。"""
        if self._task is None:
            raise TimerAlreadyStopped("既にポモドーロタイマーは停止しています。")

        task = self._task
        self._task = None

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            # `logger.exception`でエラーのログは出している。
            # ユーザーに終了したことは確実に伝えたいので、エラーはsuppressする。
            await task

        if self._last_notification is not None:
            content = format_pinned_phase_status(
                self._last_notification.kind,
                self._last_notification.ends_at,
                self._has_phase_switched,
            )
            await self._last_notification.message.edit(content=content)

    def pause(self) -> None:
        """タイマーの一時停止を行う。"""
        self._timer.pause()

    def resume(self) -> None:
        """タイマーの再開する。"""
        self._timer.resume()


def format_time_until(target: float) -> str:
    """Discordのタイムスタンプでリアルタイムに変化する「N分後」のメンションを作成する。"""
    return f"<t:{math.ceil(target)}:R>"


def format_phase_status(kind: str, ends_at: float, has_phase_switched: bool) -> str:
    formated_ends_at = format_time_until(ends_at)

    if not has_phase_switched:
        return (
            "🍅 ポモドーロタイマー\n"
            f"フェーズ「{kind}」が開始しました。\n"
            f"次のフェーズは{formated_ends_at}となります。"
        )

    return (
        "🍅 ポモドーロタイマー\n"
        f"「{kind}」の時間となりました。\n"
        f"次のフェーズは{formated_ends_at}となります。"
    )


def format_pinned_time_until(target: float) -> str:
    """Discordのタイムスタンプ表示を模倣した、メンションでない普通のテキストを作成する。"""
    remaining = target - time()

    if remaining <= 0:
        return "0秒後"

    if remaining >= 3600:
        hours = math.ceil(remaining / 3600)
        return f"{hours}時間後"

    if remaining >= 60:
        minutes = math.ceil(remaining / 60)
        return f"{minutes}分後"

    return f"{remaining:.0f}秒後"


def format_pinned_phase_status(
    kind: str, ends_at: float, has_phase_switched: bool
) -> str:
    """Discordのタイムスタンプを使わない、フェーズ状況通知メッセージの内容を作成する。"""
    formated_ends_at = format_pinned_time_until(ends_at)

    if not has_phase_switched:
        return (
            "🍅 ポモドーロタイマー\n"
            f"フェーズ「{kind}」が開始しました。\n"
            f"次のフェーズは{formated_ends_at}となります。"
        )

    return (
        "🍅 ポモドーロタイマー\n"
        f"「{kind}」の時間となりました。\n"
        f"次のフェーズは{formated_ends_at}となります。"
    )


class SessionException(Exception):
    """``SessionManager``で起きうるエラー"""


class SessionAlreadyCreated(SessionException):
    """既にセッションが作られている際のエラー"""


class SessionNotFound(SessionException):
    """登録されていないセッションを扱おうとした際のエラー"""


class SessionManager:
    """ポモドーロのセッションを管理するサービス"""

    def __init__(self) -> None:
        self._sessions = dict[int, TimerSession]()

    async def teardown(self, *, timeout: int = 3) -> None:
        """セッション管理を終了します。

        稼働中のセッションは終了処理を開始し、``timeout``まではVCのgracefulな切断を試みます。
        """
        semaphore = asyncio.Semaphore(3)

        async def disconnect(session: TimerSession) -> None:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                async with semaphore:
                    await session.stop()
                    await session.disconnect()

            await asyncio.sleep(0.3)

        disconnect_all_future = asyncio.gather(
            *(disconnect(session) for session in self._sessions.values())
        )

        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(disconnect_all_future, timeout=timeout)

    def is_created(self, guild_id: int) -> bool:
        """既にセッションが作られているかどうか"""
        return guild_id in self._sessions

    async def connect(
        self,
        routine: Routine,
        *,
        text_channel: discord.abc.Messageable,
        voice_channel: discord.VoiceChannel | discord.StageChannel,
        alarm_sound_path: PurePath,
    ) -> None:
        """VCに接続してポモドーロセッションを作成する。"""
        if voice_channel.guild.id in self._sessions:
            raise SessionAlreadyCreated(voice_channel.guild)

        session = await TimerSession.connect(
            routine,
            text_channel=text_channel,
            voice_channel=voice_channel,
            alarm_sound_path=alarm_sound_path,
        )
        self._sessions[voice_channel.guild.id] = session

    def start(self, guild_id: int) -> None:
        """ポモドーロタイマーを開始する。"""
        try:
            self._sessions[guild_id].start()
        except KeyError:
            raise SessionNotFound

    async def stop(self, guild_id: int, *, force: bool = False) -> None:
        """ポモドーロセッションを終了する。"""
        session = self._sessions.get(guild_id)
        if session is None:
            raise SessionNotFound

        with contextlib.suppress(TimerAlreadyStopped):
            await session.stop()
        self._sessions.pop(guild_id, None)
        await session.disconnect(force=force)

    def pause(self, guild_id: int) -> None:
        try:
            self._sessions[guild_id].pause()
        except KeyError:
            raise SessionNotFound

    def resume(self, guild_id: int) -> None:
        try:
            self._sessions[guild_id].resume()
        except KeyError:
            raise SessionNotFound
