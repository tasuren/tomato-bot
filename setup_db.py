"""``setup_db.sql``を実行してデータベースを用意する。"""

import sqlite3
from os import getenv
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

# データベースのパスを取得する。
database_url: Final = getenv("DATABASE_URL")
if database_url is None:
    raise Exception("環境変数`DATABASE_URL`を設定してください。")
parsed = urlparse(database_url)
path = parsed.path.lstrip("/")

# データベースにテーブルを反映させる。
conn = sqlite3.connect(path)

error = None
try:
    current_dir = Path(__file__).resolve().parent
    sql_path = current_dir / "setup_db.sql"
    sql = sql_path.read_text(encoding="utf-8")

    conn.executescript(sql)
    conn.commit()
except Exception as e:
    error = e

# tryを使って確実にデータベースの接続は終了する。
conn.close()

if error is not None:
    raise error
