from __future__ import annotations

__all__ = (
    "DEFAULT_ROUTINES",
    "FALLBACK_ROUTINE",
    "DEFAULT_ALARM_SOUNDS",
    "FALLBACK_ALARM_SOUND",
)

from tomato_bot.domain import AlarmSoundMetadata, Phase, RoutineMetadata

DEFAULT_ALARM_SOUNDS: tuple[AlarmSoundMetadata, ...] = (
    AlarmSoundMetadata("標準（電子音「ピピピピ」）", None, "alarm_standard.wav"),
)
FALLBACK_ALARM_SOUND: AlarmSoundMetadata = DEFAULT_ALARM_SOUNDS[0]


DEFAULT_ROUTINES: tuple[RoutineMetadata, ...] = (
    RoutineMetadata(
        "標準",
        "２５分作業５分休憩",
        1,
        (
            Phase(kind="作業", duration=60 * 25),
            Phase(kind="休憩", duration=60 * 5),
        ),
    ),
    RoutineMetadata(
        "標準（大休憩あり）",
        "「２５分作業５分休憩」が３回、「２５分作業１５分休憩」が１回",
        1,
        (
            Phase(kind="作業", duration=60 * 25),
            Phase(kind="休憩", duration=60 * 5),
            Phase(kind="作業", duration=60 * 25),
            Phase(kind="休憩", duration=60 * 5),
            Phase(kind="作業", duration=60 * 25),
            Phase(kind="休憩", duration=60 * 5),
            # 25分作業15分休憩
            Phase(kind="作業", duration=60 * 25),
            Phase(kind="休憩", duration=60 * 15),
        ),
    ),
    RoutineMetadata(
        "集中",
        "５０分作業１０分休憩",
        1,
        (
            Phase(kind="作業", duration=60 * 50),
            Phase(kind="休憩", duration=60 * 10),
        ),
    ),
)
FALLBACK_ROUTINE: RoutineMetadata = DEFAULT_ROUTINES[0]
