"""
SSA 日次スクレイピング スタンドアロンスクリプト
Windowsタスクスケジューラから毎朝実行する

使い方:
  python scripts/daily_scrape.py              # 昨日のデータを取得
  python scripts/daily_scrape.py 2026-04-07   # 指定日のデータを取得

タスクスケジューラ設定:
  プログラム: C:\\Python312\\python.exe
  引数:       C:\\Users\\houmo\\sakuraSSAkanri\\scripts\\daily_scrape.py
  開始場所:   C:\\Users\\houmo\\sakuraSSAkanri
  実行時刻:   毎朝 09:00
"""
import sys
import os
import logging
from datetime import date, datetime

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ロギング設定（ファイルにも出力）
os.makedirs("instance/logs", exist_ok=True)
log_file = f"instance/logs/scrape_{datetime.now().strftime('%Y%m')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# .env を読み込む
from dotenv import load_dotenv
load_dotenv()

# Flask アプリコンテキスト内で実行
from app import create_app

app = create_app()

with app.app_context():
    from app.services.ssa_scraper import scrape_and_save

    # 引数で日付指定があれば使用
    target_date = None
    if len(sys.argv) > 1:
        try:
            target_date = date.fromisoformat(sys.argv[1])
            logger.info(f"指定日: {target_date}")
        except ValueError:
            logger.error(f"日付フォーマットエラー: {sys.argv[1]} (YYYY-MM-DD 形式で指定してください)")
            sys.exit(1)

    result = scrape_and_save(target_date)

    if result["error"]:
        logger.error(f"取得失敗: {result['error']}")
        sys.exit(1)
    else:
        logger.info(f"取得成功: {result['date']} / {result['fetched']}件取得 / {result['saved']}件保存")
        sys.exit(0)
