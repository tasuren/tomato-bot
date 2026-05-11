from __future__ import annotations

__all__ = (
    "token",
    "database_url",
    "override_about_text",
    "override_help_text",
    "loading_emoji",
)

from os import getenv

import discord
from dotenv import load_dotenv

load_dotenv()


def token() -> str:
    token = getenv("TOKEN")
    if token is None:
        raise RuntimeError("環境変数`TOKEN`を設定してください。")
    return token


def database_url() -> str:
    database_url = getenv("DATABASE_URL")
    if database_url is None:
        raise RuntimeError("環境変数`DATABASE_URL`を設定してください。")
    return database_url


def override_about_text() -> str | None:
    return getenv("ABOUT_TEXT") or None  # 空文字だった場合でも確実に`None`にする。


def override_help_text() -> str | None:
    return getenv("HELP_TEXT") or None  # 空文字だった場合でも確実に`None`にする。


def loading_emoji() -> str:
    return getenv("LOADING_EMOJI") or "⏳"


# 設定のバリデーション
token()  # tokenが設定されているか確認するだけ。
database_url()  # database urlが設定されているか確認するだけ

# Opusの設定
opus_lib_path = getenv("OPUS_LIB_PATH")

if not discord.opus.is_loaded():
    if opus_lib_path is None:
        raise Exception(
            "Opusライブラリを探したところ、見つかりませんでした。"
            "環境変数`OPUS_LIB_PATH`でパスを設定してください。"
        )

    discord.opus.load_opus(opus_lib_path)
