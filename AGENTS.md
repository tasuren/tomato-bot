# AGENTS.md

ポモドーロタイマーをVCで動かすためのDiscord Botプロジェクトです。
Discord初心者でも使いやすいUIを目指しています。

## 技術スタック

- Python
- discord.py
- SQLite

## フォルダ構成

実装上の構成:

- `src/tomato_bot/application`: アプリケーション層
- `src/tomato_bot/domain`: ドメイン層
- `src/tomato_bot/ui`: DiscordのUI
- `src/tomato_bot/repository.py`: データベース管理
- `src/tomato_bot/bot.py`: コンポジションルート

運用上の構成:

- `data/`: Botがファイルを配置する場所（例: SQLite）
- `data/audio/default`: デフォルトのアラーム音の配置場所
- `data/audio/guild`: サーバーのアラーム音の配置場所（未実装）

## ツール

- `uv`でPythonプロジェクト環境の管理が可能
- `uv run ruff`でRuffによりlint/formatが使用可能

## コミット

Conventional Commitsベースの日本語でお願いします。
まだ規模が浅いところなので、特に指定されない限り、
今の所スコープを指定する必要はありません。
