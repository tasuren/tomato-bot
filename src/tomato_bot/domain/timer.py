from __future__ import annotations

__all__ = (
    "PhaseStarted",
    "PhaseChanged",
    "PomodoroTimer",
    "PhasePaused",
    "PhaseResumed",
    "TimerStateError",
    "TimerAlreadyPaused",
    "TimerAlreadyResumed",
)

import asyncio
import time
from dataclasses import dataclass

from tomato_bot.domain.routine import Phase, Routine


@dataclass(kw_only=True)
class TimerState:
    """ポモドーロタイマーを実際に動かしている状況を表す状態

    その時その時、どのフェーズにいるかなどを格納する。
    """

    routine: Routine
    "現在、適用中のフェーズ"
    index: int = 0
    """何セッション目か

    現在のフェーズを指す``routine.phases``におけるindex。"""
    is_started: bool = False
    "ポモドーロタイマーが既に動作しているかどうか"

    @property
    def current_phase(self) -> Phase:
        """現在進行中のフェーズ"""
        return self.routine.phases[self.index]

    @property
    def next_phase(self) -> Phase:
        """次に予定しているフェーズ"""
        next_index = self.index + 1
        if next_index == len(self.routine.phases):
            return self.routine.phases[0]
        return self.routine.phases[next_index]

    def advance_phase(self) -> None:
        """フェーズを次に進める。"""
        self.index += 1
        if self.index == len(self.routine.phases):
            self.index = 0  # 一周した場合


@dataclass(frozen=True, kw_only=True)
class PhaseStarted:
    """フェーズが開始した際のイベント"""

    phase: Phase
    ends_at: float


@dataclass(frozen=True, kw_only=True)
class PhaseChanged:
    """フェーズが切り替わった際のイベント"""

    phase: Phase
    ends_at: float


@dataclass(frozen=True, kw_only=True)
class PhasePaused:
    """フェーズが一時停止された際のイベント"""

    phase: Phase
    remaining: float


@dataclass(frozen=True, kw_only=True)
class PhaseResumed:
    """フェーズが再開された際のイベント"""

    phase: Phase
    new_ends_at: float


type TimerEvent = PhaseStarted | PhaseChanged | PhasePaused | PhaseResumed
"ポモドーロタイマーの動作イベント"


class PauseController:
    """一時停止と再開の排他制御をするためのクラス"""

    def __init__(self) -> None:
        self._pause_event = asyncio.Event()
        self._resume_event = asyncio.Event()

        self.resume()

    def pause(self) -> None:
        self._pause_event.set()
        self._resume_event.clear()

    def resume(self) -> None:
        self._resume_event.set()
        self._pause_event.clear()

    async def wait_pause(self) -> None:
        await self._pause_event.wait()

    async def wait_resume(self) -> None:
        await self._resume_event.wait()

    def is_paused(self) -> bool:
        return self._pause_event.is_set()

    def is_resumed(self) -> bool:
        return self._resume_event.is_set()


class TimerStateError(Exception):
    """タイマー状態が操作と整合しない場合のエラー"""


class TimerAlreadyPaused(TimerStateError):
    """既に一時停止中のタイマーを一時停止しようとした"""


class TimerAlreadyResumed(TimerStateError):
    """既に再開中のタイマーを再開しようとした"""


class TimerNotStarted(TimerStateError):
    """タイマーはまだ開始していません。"""


class PomodoroTimer:
    """ポモドーロタイマーの実装"""

    def __init__(self, routine: Routine) -> None:
        self._state = TimerState(routine=routine)
        self._pause_controller = PauseController()
        self._events = asyncio.Queue[TimerEvent]()

    @property
    def events(self) -> asyncio.Queue[TimerEvent]:
        return self._events

    def resume(self) -> None:
        """ポモドーロタイマーを再開する。"""
        if not self._state.is_started:
            raise TimerNotStarted
        if self._pause_controller.is_resumed():
            raise TimerAlreadyResumed
        self._pause_controller.resume()

    def pause(self) -> None:
        """ポモドーロタイマーを停止する。"""
        if not self._state.is_started:
            raise TimerNotStarted
        if self._pause_controller.is_paused():
            raise TimerAlreadyPaused
        self._pause_controller.pause()

    async def run(self) -> None:
        """ポモドーロタイマーを開始する。"""
        self._state.is_started = True

        ends_at = time.time() + self._state.current_phase.duration
        self._events.put_nowait(
            PhaseStarted(phase=self._state.current_phase, ends_at=ends_at)
        )

        while True:
            await self._sleep_phase()
            self._state.advance_phase()

            ends_at = time.time() + self._state.current_phase.duration
            self._events.put_nowait(
                PhaseChanged(phase=self._state.current_phase, ends_at=ends_at)
            )

    async def _sleep_phase(self) -> None:
        # 一つ分、フェーズの待機を行う。
        # 途中に一時停止されるケースに対応するため、while文を使う。

        remaining = self._state.current_phase.duration

        while remaining > 0:
            started_at = time.monotonic()

            phase_sleep = asyncio.create_task(asyncio.sleep(remaining))
            pause_receiver = asyncio.create_task(self._pause_controller.wait_pause())

            done, pending = await asyncio.wait(
                (phase_sleep, pause_receiver), return_when=asyncio.FIRST_COMPLETED
            )

            for task in pending:
                task.cancel()

            # 最後までフェーズの長さ分の待機タスクが完遂したのなら、
            # ここでこのフェーズの待機は終了。
            if phase_sleep in done:
                return

            # フェーズの待機（`phase_sleep`）が終わらなかったのなら、
            # 一時停止されたということ。なので残り時間をメモしておく。
            # これにより、再開後に適切な残り時間となる。
            remaining -= time.monotonic() - started_at
            self._events.put_nowait(
                PhasePaused(phase=self._state.current_phase, remaining=remaining)
            )

            # 一時停止が解除されるまで待機する。
            await self._pause_controller.wait_resume()
            self._events.put_nowait(
                PhaseResumed(
                    phase=self._state.current_phase, new_ends_at=time.time() + remaining
                )
            )
