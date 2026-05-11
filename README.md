# トマトBot

ポモドーロタイマーをVCで動かすためのDiscord Bot。
カスタムルーチン機能を搭載し、初心者でも使いやすいUIを目指しています。

**クローズドベータ公開中、近日公開**

## 開発方法

### フォルダ構成

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

### セットアップ

パッケージマネージャuvを使用します。

1. `uv sync --sync`で依存関係をインストールする。
2. `.env.example`を参考に環境変数を設定（`.env`でも可）
3. `uv run setup_db.py`を実行してデータベースを用意
4. `uv run -m tomato_bot --sync-global-commands-first`で起動しコマンドの同期を行う

コマンドの変更が発生しない限り、一度`--sync-global-commands-first`を実行しているなら、
起動は`uv run -m tomato_bot`で問題ございません。

## 謝辞

`data/audio/default` にある `alarm_standard.wav` は、[OtoLogic](https://otologic.jp?utm_source=chatgpt.com) が提供するサウンド素材（CC BY 4.0）です。  
トマトBotのデフォルトアラーム音として使用しています。ありがとうございます。

## ライセンス

このリポジトリは[Apache License 2.0](./LICENSE)の下で公開されています。
