from __future__ import annotations

__all__ = ("Routine", "Phase", "RoutineMetadata")

from dataclasses import dataclass
from typing import NamedTuple


@dataclass(kw_only=True)
class Routine:
    """ポモドーロタイマーの設定

    例:
    * 通常（25分作業5分休憩）
    * 大休憩あり（「25分作業5分休憩」を3回「25分作業15分休憩」を1回）
    """

    id: int
    "設定ID"
    name: str
    "設定名"
    description: str
    "設定の説明"
    guild_id: int
    "サーバーID"
    user_id: int | None
    "ユーザー設定だった場合、どのユーザーが設定したものか"
    alarm_sound_id: int
    "設定されているアラーム音の名前"
    phases: list[Phase]
    "〜分〜する、という具合のフェーズ"

    def __post_init__(self) -> None:
        if len(self.phases) == 0:
            raise ValueError("`phases`は１個以上設定、されている必要があります。")

    @property
    def is_user_preference(self) -> bool:
        """ユーザーの個人設定かどうか"""
        return self.user_id is not None


@dataclass(kw_only=True)
class Phase:
    """ポモドーロタイマーのフェーズ

    例えば、作業時間、休憩時間、など。
    """

    kind: str
    "種別（例: 休憩）"
    duration: int
    "長さ（秒数）"


class RoutineMetadata(NamedTuple):
    """ルーチン設定のテンプレート"""

    name: str
    description: str
    alarm_sound_id: int
    phases: tuple[Phase, ...]
