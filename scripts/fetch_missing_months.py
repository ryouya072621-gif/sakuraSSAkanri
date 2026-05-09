"""2026年2月・3月の欠損データを取得"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from datetime import date
from app import create_app
from app.services.ssa_scraper import scrape_and_save

app = create_app()

MONTHS = [
    date(2026, 2, 1),   # 2月の代表日
    date(2026, 3, 1),   # 3月の代表日
]

with app.app_context():
    for target in MONTHS:
        print(f"\n--- {target.strftime('%Y年%m月')} を取得中 ---")
        result = scrape_and_save(target)
        if result["error"]:
            print(f"  エラー: {result['error']}")
        else:
            print(f"  取得: {result['fetched']}件 / 保存: {result['saved']}件")
