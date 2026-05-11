from __future__ import annotations

__all__ = ("resolve_alarm_sound",)

from pathlib import PurePath

from pathvalidate import sanitize_filename

from tomato_bot.default_settings import FALLBACK_ALARM_SOUND
from tomato_bot.domain import AlarmSoundFileRef


def resolve_alarm_sound(alarm_sound: AlarmSoundFileRef | None) -> PurePath:
    """指定されたアラーム音の設定から、実際のアラーム音がある場所を解決する。"""
    if alarm_sound is None:
        return PurePath(f"data/audio/default/{FALLBACK_ALARM_SOUND.audio_file_name}")

    file_name = sanitize_filename(alarm_sound.file_name)
    scope = "default" if alarm_sound.is_default else "guild"
    return PurePath(f"data/audio/{scope}/{file_name}")
