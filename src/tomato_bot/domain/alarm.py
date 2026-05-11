from __future__ import annotations

__all__ = ("AlarmSoundFileRef", "AlarmSoundMetadata")

from typing import NamedTuple


class AlarmSoundFileRef(NamedTuple):
    """アラーム音のファイル"""

    file_name: str
    is_default: bool


class AlarmSoundMetadata(NamedTuple):
    """アラーム音の設定のテンプレート"""

    name: str
    guild_id: int | None
    audio_file_name: str
