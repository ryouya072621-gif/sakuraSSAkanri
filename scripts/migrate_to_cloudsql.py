"""
ローカルSQLite → Cloud SQL (PostgreSQL) データ移行スクリプト
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ローカルSQLite
SQLITE_URL = 'sqlite:///instance/app.db'

# Cloud SQL接続（Cloud SQL Auth Proxy経由 or 直接接続）
# 実行前に: gcloud sql connect ssasakura-db --user=ssasakura-user --database=ssasakura
# または Cloud SQL Auth Proxy起動後に以下のURLを設定
CLOUD_SQL_URL = os.environ.get('TARGET_DB_URL', '')

if not CLOUD_SQL_URL:
    print("ERROR: TARGET_DB_URL 環境変数を設定してください")
    print("例: export TARGET_DB_URL='postgresql://ssasakura-user:PASSWORD@34.104.137.13/ssasakura'")
    sys.exit(1)

print(f"移行元: SQLite (instance/app.db)")
print(f"移行先: PostgreSQL (Cloud SQL)")

# SQLite接続
sqlite_engine = create_engine(SQLITE_URL)
SqliteSession = sessionmaker(bind=sqlite_engine)

# PostgreSQL接続
pg_engine = create_engine(CLOUD_SQL_URL, connect_args={'connect_timeout': 10})
PgSession = sessionmaker(bind=pg_engine)

def migrate_table(table_name, sqlite_conn, pg_conn):
    rows = sqlite_conn.execute(text(f"SELECT * FROM {table_name}")).fetchall()
    if not rows:
        print(f"  {table_name}: 0件（スキップ）")
        return 0

    cols = sqlite_conn.execute(text(f"SELECT * FROM {table_name} LIMIT 1")).keys()
    col_list = list(cols)

    # PostgreSQLにINSERT（競合時はスキップ）
    placeholders = ', '.join([f':{c}' for c in col_list])
    col_names = ', '.join(col_list)
    insert_sql = text(f"""
        INSERT INTO {table_name} ({col_names})
        VALUES ({placeholders})
        ON CONFLICT DO NOTHING
    """)

    count = 0
    for row in rows:
        row_dict = dict(zip(col_list, row))
        pg_conn.execute(insert_sql, row_dict)
        count += 1

    pg_conn.commit()
    print(f"  {table_name}: {count}件 移行完了")
    return count

# テーブル移行順序（外部キー考慮）
TABLES = [
    'display_categories',
    'category_keywords',
    'app_settings',
    'unit_type_rules',
    'work_records',
    'ai_insight_cache',
]

with sqlite_engine.connect() as sqlite_conn, pg_engine.connect() as pg_conn:
    # まずDDL実行（テーブル作成）
    print("\n[1] テーブル作成中...")
    from app import create_app
    app = create_app()
    print("  テーブル作成完了")

    print("\n[2] データ移行中...")
    total = 0
    for table in TABLES:
        try:
            n = migrate_table(table, sqlite_conn, pg_conn)
            total += n
        except Exception as e:
            print(f"  {table}: エラー - {e}")

    print(f"\n完了: 合計 {total} 件移行")
