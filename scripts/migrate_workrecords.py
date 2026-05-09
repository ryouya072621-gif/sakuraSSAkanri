"""work_recordsのみCloud SQLへ移行"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import sqlite3
from google.cloud.sql.connector import Connector
import sqlalchemy

connector = Connector()
def get_conn():
    return connector.connect(
        'elite-campus-480105-h9:asia-northeast1:ssasakura-db',
        'pg8000', user='ssasakura-user', password='eOaI39slLwQwVIRkyXUK', db='ssasakura'
    )

pg_engine = sqlalchemy.create_engine('postgresql+pg8000://', creator=get_conn)
sqlite_conn = sqlite3.connect('instance/app.db')

# PostgreSQLのwork_recordsカラムを取得
with pg_engine.connect() as conn:
    result = conn.execute(sqlalchemy.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='work_records' ORDER BY ordinal_position"
    ))
    pg_cols = [r[0] for r in result.fetchall()]

print(f'PGカラム数: {len(pg_cols)}')

# SQLiteから共通カラムのみ取得
col_list = ', '.join(pg_cols)
all_rows = sqlite_conn.execute(f"SELECT {col_list} FROM work_records").fetchall()
print(f'SQLite件数: {len(all_rows)}')

placeholders = ', '.join([':' + c for c in pg_cols])

inserted = 0
BATCH = 500
for i in range(0, len(all_rows), BATCH):
    batch = all_rows[i:i+BATCH]
    with pg_engine.begin() as conn:
        for row in batch:
            row_dict = dict(zip(pg_cols, row))
            r = conn.execute(
                sqlalchemy.text(f"INSERT INTO work_records ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"),
                row_dict
            )
            if r.rowcount > 0:
                inserted += 1
    print(f'  {i+len(batch)}/{len(all_rows)}件処理... ({inserted}件挿入)')

# 結果確認
with pg_engine.connect() as conn:
    total = conn.execute(sqlalchemy.text('SELECT COUNT(*) FROM work_records')).scalar()
    by_month = conn.execute(sqlalchemy.text(
        "SELECT TO_CHAR(work_date,'YYYY-MM') as ym, COUNT(*) FROM work_records GROUP BY ym ORDER BY ym"
    )).fetchall()

print(f'\nCloud SQL合計: {total}件')
for r in by_month:
    print(f'  {r[0]}: {r[1]}件')

connector.close()
sqlite_conn.close()
