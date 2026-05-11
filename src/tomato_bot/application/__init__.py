from __future__ import annotations

__all__ = ("ApplicationServices",)

from typing import TYPE_CHECKING

from tomato_bot.application.command_use_case import CommandUseCase
from tomato_bot.application.guild_initialize import GuildInitializeService
from tomato_bot.application.session_manager import SessionManager

if TYPE_CHECKING:
    from tomato_bot.bot import TomatoBot


class ApplicationServices:
    """アプリケーションサービスをまとめるためのクラス"""

    def __init__(self, bot: TomatoBot) -> None:
        self._bot = bot

        self.guild_initializer = GuildInitializeService(bot)
        self.sessions = SessionManager()

        self.command_use_case = CommandUseCase(
            repository=bot.repository, sessions=self.sessions
        )
