from __future__ import annotations

__all__ = ("Repository", "SQLiteRepository", "NewRoutineRecord")

import asyncio
import itertools
import json
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Collection, Iterable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import asdict, dataclass
from typing import Any, TypedDict, override
from urllib.parse import urlparse

import aiosqlite

from tomato_bot.domain import AlarmSoundFileRef, Phase, Routine


class Repository(ABC):
    """リポジトリのインターフェース"""

    @abstractmethod
    async def connect(self, database_url: str) -> None:
        """データベースに接続してこのリポジトリを使える状態にする。"""

    @abstractmethod
    async def close(self) -> None:
        """データベースとの接続をcloseする。"""

    @abstractmethod
    def transaction(self) -> AbstractAsyncContextManager[None, Any]:
        """トランザクションを作成し、同時に複数のタスクが書き込みを行わないようにする。"""

    @abstractmethod
    async def insert_guild_settings_if_missing(
        self, guild_ids: Collection[int]
    ) -> None:
        """``guild_ids``の全てのサーバー設定の行がある状態を保証する。"""

    @abstractmethod
    async def get_uninitialized_guild_ids(
        self, guild_ids: Collection[int]
    ) -> list[int]:
        """``guild_ids``のうち、デフォルト設定が反映されていないサーバーを収集する。"""

    @abstractmethod
    async def insert_routines(self, routines: Iterable[NewRoutineRecord]) -> None:
        """ルーチン設定を指定されたサーバー群に対して追加する。"""

    @abstractmethod
    async def mark_guilds_initialized(self, guild_ids: Collection[int]) -> None:
        """指定されたサーバー群を初期化済みとマークしておく。"""

    @abstractmethod
    async def get_available_routines(
        self, guild_id: int, user_id: int
    ) -> list[Routine]:
        """指定されたサーバーとユーザーにおいて、使用可能なルーチンを取得する。"""

    @abstractmethod
    async def get_alarm_sound_file(self, id: int) -> AlarmSoundFileRef | None:
        """指定されたIDのアラーム音のファイル名を取得する。"""


class SQLiteRepository(Repository):
    """SQLiteを使ったリポジトリの実装"""

    db: aiosqlite.Connection

    def __init__(self) -> None:
        # `ensure_guild_initialized`の処理中にコミットがされると不整合が起きる懸念がある。
        # だからコミットが伴う処理は同時に一個までとする。
        self._commit_lock = asyncio.Lock()

    @override
    async def connect(self, database_url: str) -> None:
        parsed = urlparse(database_url)
        path = parsed.path.lstrip("/")
        self.db = await aiosqlite.connect(path)

    @override
    async def close(self) -> None:
        await self.db.close()

    @override
    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None, None]:
        async with self._commit_lock:
            try:
                await self.db.execute("BEGIN;")
                yield
            except Exception:
                await self.db.rollback()
                raise
            else:
                await self.db.commit()

    @override
    async def insert_guild_settings_if_missing(
        self, guild_ids: Collection[int]
    ) -> None:
        await self.db.executemany(
            """
            INSERT OR IGNORE INTO guild_settings (guild_id, initialized)
            VALUES (?, ?);
            """,
            map(lambda gid: (gid, False), guild_ids),
        )

    @override
    async def get_uninitialized_guild_ids(
        self, guild_ids: Collection[int]
    ) -> list[int]:
        if not guild_ids:
            return []

        guild_filter = "(" + ",".join("?" for _ in guild_ids) + ")"
        async with self.db.execute(
            f"""
            SELECT guild_id FROM guild_settings
            WHERE NOT initialized AND guild_id IN {guild_filter} LIMIT ?;
            """,
            tuple(itertools.chain(guild_ids, (len(guild_ids),))),
        ) as cursor:
            not_initialized = list[int]()
            async for (guild_id,) in cursor:
                not_initialized.append(guild_id)

            return not_initialized

    @override
    async def insert_routines(self, routines: Iterable[NewRoutineRecord]) -> None:
        await self.db.executemany(
            """
            INSERT INTO routines (name, description, guild_id, alarm_sound_id, phases)
            VALUES (?, ?, ?, ?, ?);
            """,
            map(
                lambda r: (
                    r.name,
                    r.description,
                    r.guild_id,
                    r.alarm_sound_id,
                    json.dumps(tuple(map(asdict, r.phases))),
                ),
                routines,
            ),
        )

    @override
    async def mark_guilds_initialized(self, guild_ids: Collection[int]) -> None:
        if not guild_ids:
            return

        guild_filter = "(" + ",".join("?" for _ in guild_ids) + ")"

        await self.db.execute(
            f"""
                UPDATE guild_settings SET initialized = true
                WHERE guild_id IN {guild_filter};
                """,
            guild_ids,
        )

    @override
    async def get_available_routines(
        self, guild_id: int, user_id: int
    ) -> list[Routine]:
        async with self.db.execute(
            "SELECT allow_user_preferences FROM guild_settings WHERE guild_id = ? LIMIT 1;",
            (guild_id,),
        ) as cursor:
            (allow_user_preferences,) = await cursor.fetchone() or (True,)

        async with self.db.execute(
            "SELECT * FROM routines WHERE guild_id = ? AND (user_id IS NULL OR ? AND user_id = ?);",
            (guild_id, allow_user_preferences, user_id),
        ) as cursor:
            routines = []

            async for row in cursor:
                id, name, description, guild_id, user_id, alarm_sound_id, raw_phases = (
                    row
                )

                phases_dto: list[PhaseDto] = json.loads(raw_phases)

                routines.append(
                    Routine(
                        id=id,
                        name=name,
                        description=description,
                        guild_id=guild_id,
                        user_id=user_id,
                        alarm_sound_id=alarm_sound_id,
                        phases=list(
                            map(lambda phase_dto: Phase(**phase_dto), phases_dto)
                        ),
                    )
                )

            return routines

    @override
    async def get_alarm_sound_file(self, id: int) -> AlarmSoundFileRef | None:
        async with self.db.execute(
            """
            SELECT guild_id IS NULL, audio_file_name
            FROM alarm_sounds
            WHERE id = ? LIMIT 1;
            """,
            (id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return

            is_default_raw, audio_file_name = row
            return AlarmSoundFileRef(audio_file_name, is_default_raw)


@dataclass(frozen=True, kw_only=True)
class NewRoutineRecord:
    """新しいルーチン設定のデータ"""

    name: str
    description: str
    guild_id: int
    user_id: int | None
    alarm_sound_id: int
    phases: Collection[Phase]


class PhaseDto(TypedDict):
    """JSONで表現する際のフェーズの辞書型"""

    kind: str
    duration: int
