from __future__ import annotations

__all__ = (
    "PhaseStarted",
    "PhaseChanged",
    "PhaseRemainingCheckpoint",
    "PhaseRemainingCheckpointKind",
    "PomodoroTimer",
    "PhasePaused",
    "PhaseResumed",
    "TimerStateError",
    "TimerAlreadyPaused",
    "TimerAlreadyResumed",
)

import asyncio
import enum
import time
from dataclasses import dataclass
from typing import Final

from tomato_bot.domain.routine import Phase, Routine

PHASE_REMAINING_CHECKPOINT_INTERVAL_SECONDS: Final = 5 * 60
PHASE_REMAINING_FINAL_CHECKPOINT_SECONDS: Final = 60


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


class PhaseRemainingCheckpointKind(enum.Enum):
    """フェーズの残り時間の区切りがどの種類か"""

    FIVE_MINUTES = enum.auto()
    ONE_MINUTE = enum.auto()


@dataclass(frozen=True, kw_only=True)
class PhaseRemainingCheckpoint:
    """フェーズの残り時間の区切りに相当するチェックポイントのイベント（例：残り５分）"""

    phase: Phase
    remaining: float
    ends_at: float
    kind: PhaseRemainingCheckpointKind


@dataclass(frozen=True, kw_only=True)
class RemainingCheckpoint:
    """残り時間チェックポイントのデータ"""

    remaining: float
    kind: PhaseRemainingCheckpointKind


type TimerEvent = (
    PhaseStarted | PhaseChanged | PhaseRemainingCheckpoint | PhasePaused | PhaseResumed
)
"ポモドーロタイマーの動作イベント"


def build_remaining_checkpoints(duration: float) -> list[RemainingCheckpoint]:
    """フェーズ時間から残り時間のチェックポイントを作成する。"""
    checkpoints: list[RemainingCheckpoint] = []

    interval = PHASE_REMAINING_CHECKPOINT_INTERVAL_SECONDS
    checkpoint_count = int(duration // interval)

    for index in range(checkpoint_count, 0, -1):
        remaining = index * interval
        if remaining >= duration:
            continue

        checkpoints.append(
            RemainingCheckpoint(
                remaining=remaining,
                kind=PhaseRemainingCheckpointKind.FIVE_MINUTES,
            )
        )

    final_checkpoint = PHASE_REMAINING_FINAL_CHECKPOINT_SECONDS
    if final_checkpoint < duration:
        checkpoints.append(
            RemainingCheckpoint(
                remaining=final_checkpoint,
                kind=PhaseRemainingCheckpointKind.ONE_MINUTE,
            )
        )

    return sorted(
        checkpoints, key=lambda checkpoint: checkpoint.remaining, reverse=True
    )


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
        checkpoints = build_remaining_checkpoints(remaining)

        while remaining > 0:
            next_checkpoint = checkpoints[0] if checkpoints else None
            wait_seconds = remaining

            if next_checkpoint is not None:
                wait_seconds = max(remaining - next_checkpoint.remaining, 0)

            started_at = time.monotonic()

            phase_sleep = asyncio.create_task(asyncio.sleep(wait_seconds))
            pause_receiver = asyncio.create_task(self._pause_controller.wait_pause())

            try:
                done, _ = await asyncio.wait(
                    (phase_sleep, pause_receiver), return_when=asyncio.FIRST_COMPLETED
                )
            finally:
                for task in (phase_sleep, pause_receiver):
                    if not task.done():
                        task.cancel()

                await asyncio.gather(
                    phase_sleep, pause_receiver, return_exceptions=True
                )

            remaining -= time.monotonic() - started_at
            if remaining < 0:
                remaining = 0

            if phase_sleep in done:
                if next_checkpoint is not None:
                    checkpoints.pop(0)
                    remaining = next_checkpoint.remaining
                    self._events.put_nowait(
                        PhaseRemainingCheckpoint(
                            phase=self._state.current_phase,
                            remaining=next_checkpoint.remaining,
                            ends_at=time.time() + remaining,
                            kind=next_checkpoint.kind,
                        )
                    )
                    continue

                # チェックポイントもこれ以上ないことから、
                # 最後までフェーズの長さ分の待機を完遂したといえる。
                # なので、ここでこのフェーズの待機は終了。

                return

            # フェーズの待機（`phase_sleep`）が終わらなかったのなら、
            # 一時停止されたということ。なので残り時間をメモしておく。
            # これにより、再開後に適切な残り時間となる。
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
