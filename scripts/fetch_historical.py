"""
SSA 過去データ一括取得スクリプト
指定した期間のデータをまとめて取得してDBに保存する

使い方:
  python scripts/fetch_historical.py                        # 過去3ヶ月
  python scripts/fetch_historical.py 2025-10-01 2026-03-31 # 期間指定
  python scripts/fetch_historical.py --months 6            # 過去6ヶ月

注意:
  - 1日ごとにブラウザを起動するため時間がかかる（1日あたり約15秒）
  - 土日祝日はデータなしの場合があるが、エラーにならず0件でスキップ
  - 途中で中断しても再実行すると重複なく続きから取得できる
"""
import sys
import os
import logging
import argparse
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.makedirs("instance/logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("instance/logs/fetch_historical.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

from app import create_app

app = create_app()


def parse_args():
    parser = argparse.ArgumentParser(description="SSA 過去データ一括取得")
    parser.add_argument("start", nargs="?", help="開始日 (YYYY-MM-DD)")
    parser.add_argument("end", nargs="?", help="終了日 (YYYY-MM-DD)")
    parser.add_argument("--months", type=int, default=3, help="過去N ヶ月分 (デフォルト: 3)")
    return parser.parse_args()


def main():
    args = parse_args()

    today = date.today()

    if args.start and args.end:
        start_date = date.fromisoformat(args.start)
        end_date = date.fromisoformat(args.end)
    else:
        end_date = today - timedelta(days=1)
        start_date = today - relativedelta(months=args.months)

    logger.info(f"取得期間: {start_date} ～ {end_date}")

    # 対象日付リスト（平日のみ）
    target_dates = []
    d = start_date
    while d <= end_date:
        if d.weekday() < 5:  # 月〜金のみ
            target_dates.append(d)
        d += timedelta(days=1)

    logger.info(f"対象日数: {len(target_dates)}日（平日のみ）")

    with app.app_context():
        from app.models import WorkRecord
        from app.services.ssa_scraper import scrape_and_save

        total_fetched = 0
        total_saved = 0
        errors = []

        for i, target_date in enumerate(target_dates, 1):
            logger.info(f"[{i}/{len(target_dates)}] {target_date} を取得中...")

            result = scrape_and_save(target_date)

            if result["error"]:
                logger.warning(f"  ✗ エラー: {result['error']}")
                errors.append({"date": str(target_date), "error": result["error"]})
            else:
                total_fetched += result["fetched"]
                total_saved += result["saved"]
                logger.info(f"  ✓ {result['fetched']}件取得 / {result['saved']}件保存")

        logger.info("=" * 50)
        logger.info(f"完了: 合計 {total_fetched}件取得 / {total_saved}件保存")
        if errors:
            logger.warning(f"エラー {len(errors)}件:")
            for e in errors:
                logger.warning(f"  {e['date']}: {e['error']}")

        # DB総件数確認
        total_records = WorkRecord.query.count()
        logger.info(f"DB総レコード数: {total_records}件")


if __name__ == "__main__":
    main()
