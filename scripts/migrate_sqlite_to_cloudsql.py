"""
SQLite → Cloud SQL (PostgreSQL) データ移行スクリプト
Cloud SQL Python Connector使用（Auth Proxy不要）
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# .envを必ず先に読み込む
from dotenv import load_dotenv
load_dotenv()

import sqlite3
from google.cloud.sql.connector import Connector
import sqlalchemy

INSTANCE = "elite-campus-480105-h9:asia-northeast1:ssasakura-db"
DB_USER  = "ssasakura-user"
DB_PASS  = "eOaI39slLwQwVIRkyXUK"
DB_NAME  = "ssasakura"
SQLITE_PATH = "instance/app.db"

print("Cloud SQL Connector で接続中...")
connector = Connector()

def get_conn():
    return connector.connect(INSTANCE, "pg8000", user=DB_USER, password=DB_PASS, db=DB_NAME)

# SQLAlchemyエンジンをCloud SQL Connector経由で直接作成
pg_engine = sqlalchemy.create_engine(
    "postgresql+pg8000://",
    creator=get_conn,
)
sqlite_conn = sqlite3.connect(SQLITE_PATH)
sqlite_conn.row_factory = sqlite3.Row

TABLES = [
    'display_categories',
    'category_keywords',
    'app_settings',
    'unit_type_rules',
    'work_records',
    'ai_insight_cache',
]

print(f"SQLite: {SQLITE_PATH}")
print(f"PostgreSQL: {INSTANCE}/{DB_NAME}\n")

# テーブル作成（Flask app経由 - Cloud SQLに接続）
print("[1] PostgreSQLにテーブル作成...")
from app import create_app, db
app = create_app()
print("    完了\n")

total = 0
print("[2] データ移行中...")
for table in TABLES:
    cur = sqlite_conn.execute(f"SELECT * FROM {table}")
    rows = cur.fetchall()
    if not rows:
        print(f"  {table}: 0件（スキップ）")
        continue

    cols = [d[0] for d in cur.description]
    col_list = ', '.join(cols)
    placeholders = ', '.join([':' + c for c in cols])

    count = 0
    skip = 0
    with pg_engine.begin() as conn:
        for row in rows:
            row_dict = dict(zip(cols, row))
            try:
                result = conn.execute(
                    sqlalchemy.text(f"""
                        INSERT INTO {table} ({col_list})
                        VALUES ({placeholders})
                        ON CONFLICT DO NOTHING
                    """),
                    row_dict
                )
                if result.rowcount > 0:
                    count += 1
                else:
                    skip += 1
            except Exception as e:
                print(f"    行エラー: {e}")
                skip += 1

    print(f"  {table}: {count}件挿入 / {skip}件スキップ（既存）")
    total += count

sqlite_conn.close()
connector.close()
print(f"\n完了: 合計 {total} 件新規挿入")
