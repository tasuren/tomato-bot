from __future__ import annotations

__all__ = ("retrieve_commands",)

from typing import TYPE_CHECKING

from discord import app_commands

if TYPE_CHECKING:
    from tomato_bot.bot import TomatoBot


_command_cache: dict[str, app_commands.AppCommand] | None = None


async def retrieve_commands(bot: TomatoBot) -> dict[str, app_commands.AppCommand]:
    """コマンドの情報を取得する。"""
    global _command_cache

    if _command_cache is None:
        commands = await bot.tree.fetch_commands()
        _command_cache = {cmd.name: cmd for cmd in commands}

    return _command_cache
