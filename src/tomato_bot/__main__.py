from __future__ import annotations

import argparse
import asyncio
import signal
from collections.abc import Sequence

import discord

from tomato_bot import config
from tomato_bot.bot import TomatoBot


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """起動時のコマンドライン引数を解析する。"""
    parser = argparse.ArgumentParser(
        prog="tomato-bot",
        description="Discord VCでポモドーロタイマーを動かすトマトBotを起動します。",
    )
    parser.add_argument(
        "--sync-global-commands-first",
        action="store_true",
        help="Botのログイン時にDiscordのグローバルコマンドを同期してから起動します。",
    )

    return parser.parse_args(argv)


async def runner(bot: TomatoBot) -> None:
    """Botを起動し、終了シグナルを受け取ったらgracefulに停止する。"""
    discord.utils.setup_logging()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    bot_task = loop.create_task(bot.start(config.token()), name="TomatoBot")
    shutdown_task = loop.create_task(stop_event.wait(), name="Shutdown waiter")

    try:
        done, _ = await asyncio.wait(
            (bot_task, shutdown_task), return_when=asyncio.FIRST_COMPLETED
        )

        if bot_task in done:
            await bot_task
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)

        shutdown_task.cancel()
        await bot.close()
        await bot_task


def main(argv: Sequence[str] | None = None) -> None:
    """コマンドライン引数を反映してBotを起動する。"""
    args = parse_args(argv)
    bot = TomatoBot(
        database_url=config.database_url(),
        sync_global_commands_first=args.sync_global_commands_first,
    )

    asyncio.run(runner(bot))


if __name__ == "__main__":
    main()
