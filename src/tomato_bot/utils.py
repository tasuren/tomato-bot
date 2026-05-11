from __future__ import annotations

__all__ = ("normalize_nested_quotes", "command_mention")

import discord


def normalize_nested_quotes(text: str, /) -> str:
    return text.replace("「", "『").replace("」", "』")


def command_mention(command: discord.app_commands.AppCommand) -> str:
    return f"</{command.name}:{command.id}>"
