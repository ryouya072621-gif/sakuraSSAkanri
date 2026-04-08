"""
SSA アプリ スクレイパー
honbu.ssa-app.com の全社売上日報CSVを自動取得してDBに保存する
"""
import os
import csv
import logging
import tempfile
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

SSA_LOGIN_URL = "https://ssa-app.com/login"
SSA_ADMIN_URL = "https://honbu.ssa-app.com"


def scrape_daily_csv(target_date: date = None) -> list:
    """
    SSA管理画面から全社売上日報CSVを取得する

    Args:
        target_date: 取得対象日（省略時は昨日）

    Returns:
        レコードのリスト [{staff_name, fetch_date, ...}, ...]
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "playwright がインストールされていません。\n"
            "pip install playwright && playwright install chromium を実行してください。"
        )

    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    email = os.environ.get("SSA_EMAIL", "")
    password = os.environ.get("SSA_PASSWORD", "")

    if not email or not password:
        raise ValueError(".env に SSA_EMAIL と SSA_PASSWORD を設定してください")

    logger.info(f"SSAスクレイピング開始: {target_date}")
    records = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            # ─── ログイン ───
            logger.info("ログイン中...")
            page.goto(SSA_LOGIN_URL, wait_until="networkidle")

            # メールとパスワードを入力
            _fill_input(page, [
                'input[placeholder="メールアドレス"]',
                'input[type="email"]',
                'input[name="email"]',
                '#email',
            ], email)
            _fill_input(page, [
                'input[placeholder="パスワード"]',
                'input[type="password"]',
                'input[name="password"]',
                '#password',
            ], password)

            # ログインボタンをクリック（unicode escapeで日本語テキスト検索 or Enter送信）
            clicked = page.evaluate(
                "Array.from(document.querySelectorAll('*'))"
                ".find(el => el.textContent.trim() === '\u30ed\u30b0\u30a4\u30f3\u3059\u308b')"
                "?.click() ?? false"
            )
            if not clicked:
                # フォールバック: Enterキーで送信
                page.keyboard.press("Enter")
            page.wait_for_load_state("networkidle")
            logger.info(f"ログイン後URL: {page.url}")

            # ─── 管理者画面へ移動（別サイトなので別途ログインが必要）───
            logger.info("管理者画面へ移動中...")
            page.goto(f"{SSA_ADMIN_URL}/#/total", wait_until="networkidle")
            page.wait_for_timeout(2000)

            # honbu.ssa-app.com は別ログイン画面 (Username/Password) にリダイレクトされる場合がある
            if "login" in page.url.lower() or page.locator('input[placeholder="Username"]').count() > 0:
                logger.info("管理者サイトのログイン画面を検出。ログイン中...")
                page.wait_for_timeout(500)
                _fill_input(page, ['input[placeholder="Username"]', 'input[name="username"]', 'input[type="text"]'], email)
                _fill_input(page, ['input[placeholder="Password"]', 'input[type="password"]', 'input[name="password"]'], password)
                # 入力確認スクリーンショット
                page.screenshot(path="instance/ssa_debug_admin_login.png")
                logger.info("管理者ログイン入力完了。ボタンクリック...")
                # ログインボタンをクリック（JSでfind）
                page.evaluate(
                    "Array.from(document.querySelectorAll('button, input[type=submit], a'))"
                    ".find(el => el.textContent.trim().length > 0 && el.offsetParent !== null)"
                    "?.click()"
                )
                page.wait_for_timeout(3000)
                logger.info(f"管理者ログイン後URL: {page.url}")
                # ログイン後に目的ページへ再移動
                page.goto(f"{SSA_ADMIN_URL}/#/total", wait_until="networkidle")
                page.wait_for_timeout(3000)
            else:
                page.wait_for_timeout(1000)

            logger.info(f"管理者画面URL: {page.url}")

            # 「全社売上日報」タブをJSでクリック
            page.evaluate("""
                const tabs = Array.from(document.querySelectorAll('a, button, [role=tab]'));
                const tab = tabs.find(el => el.textContent.includes('\u5168\u793e\u58f2\u4e0a\u65e5\u5831'));
                if (tab) tab.click();
            """)
            page.wait_for_timeout(1500)

            # ─── 日付を設定 ───
            date_str = target_date.strftime("%Y-%m-%d")
            date_input = page.locator('input[type="date"]')
            if date_input.count() > 0:
                date_input.first.fill(date_str)
                page.wait_for_timeout(1000)
                # 更新/検索ボタンをJSでクリック
                page.evaluate("""
                    const btns = Array.from(document.querySelectorAll('button'));
                    const keywords = ['\u66f4\u65b0', '\u691c\u7d22', '\u8868\u793a'];
                    const btn = btns.find(b => keywords.some(k => b.textContent.includes(k)));
                    if (btn) btn.click();
                """)
                page.wait_for_timeout(1500)

            # ─── CSVダウンロード ───
            logger.info("CSVダウンロード中...")
            # CSVダウンロードボタンをJSで探す
            csv_btn_exists = page.evaluate(
                "Array.from(document.querySelectorAll('button, a')).some(b => b.textContent.includes('CSV'))"
            )
            if not csv_btn_exists:
                raise RuntimeError("CSVDownload button not found. Page may have changed.")

            with page.expect_download(timeout=30000) as dl_info:
                page.evaluate("""
                    const btns = Array.from(document.querySelectorAll('button, a'));
                    const btn = btns.find(b => b.textContent.includes('CSV'));
                    if (btn) btn.click();
                """)
            download = dl_info.value

            # CSVを保存してパース（デバッグ用にinstance/にも保存）
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
                tmp_path = tmp.name
            download.save_as(tmp_path)

            # デバッグ用にコピー保存
            import shutil
            debug_csv = f"instance/ssa_debug_{target_date}.csv"
            shutil.copy(tmp_path, debug_csv)
            logger.info(f"CSV保存: {debug_csv}")

            records = _parse_csv(tmp_path, target_date)
            logger.info(f"取得完了: {len(records)}件")

        except Exception as e:
            # デバッグ用スクリーンショット
            try:
                screenshot_path = f"instance/ssa_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                os.makedirs("instance", exist_ok=True)
                page.screenshot(path=screenshot_path)
                logger.error(f"エラー発生。スクリーンショット保存: {screenshot_path}")
            except Exception:
                pass
            raise e
        finally:
            browser.close()
            # 一時ファイル削除
            try:
                if 'tmp_path' in locals() and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception:
                pass

    return records


def _fill_input(page, selectors: list, value: str):
    """複数のセレクタを順に試してinputに値を入力する"""
    for sel in selectors:
        el = page.locator(sel)
        if el.count() > 0:
            el.first.fill(value)
            return
    raise RuntimeError(f"入力フィールドが見つかりません。試したセレクタ: {selectors}")


def _parse_csv(csv_path: str, fetch_date: date) -> list:
    """
    SSA CSVをパースして WorkRecord 用レコードのリストを返す

    CSVの列構造（全社売上日報 > CSVダウンロード）:
    請求日, 請求元, 請求先, 仕事分類1, 仕事分類2, 仕事, 単価, 数量, 合計, 状態
    """
    records = []

    # エンコーディングを順に試す
    for encoding in ["utf-8-sig", "utf-8", "shift-jis", "cp932"]:
        try:
            with open(csv_path, "r", encoding=encoding) as f:
                content = f.read()
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RuntimeError("CSVファイルのエンコーディングを判定できませんでした")

    reader = csv.DictReader(content.splitlines())
    headers = reader.fieldnames or []
    logger.info(f"CSV列名: {headers}")

    for row in reader:
        staff_name = (row.get("\u8acb\u6c42\u5143") or "").strip()  # 請求元
        if not staff_name:
            continue

        # 請求日をパース
        date_str = (row.get("\u8acb\u6c42\u65e5") or "").strip()  # 請求日
        try:
            work_date = date.fromisoformat(date_str) if date_str else fetch_date
        except ValueError:
            work_date = fetch_date

        record = {
            "work_date": work_date,
            "staff_name": staff_name,
            "department": (row.get("\u8acb\u6c42\u5148") or "").strip(),          # 請求先
            "category1": (row.get("\u4ed5\u4e8b\u5206\u985e1") or "").strip(),    # 仕事分類1
            "category2": (row.get("\u4ed5\u4e8b\u5206\u985e2") or "").strip(),    # 仕事分類2
            "work_name": (row.get("\u4ed5\u4e8b") or "").strip(),                 # 仕事
            "unit_price": _to_int(row.get("\u5358\u4fa1")),                       # 単価
            "quantity": _to_int(row.get("\u6570\u91cf")),                         # 数量
            "total_amount": _to_int(row.get("\u5408\u8a08")),                     # 合計
            "status": (row.get("\u72b6\u614b") or "").strip(),                    # 状態
            "source_month": work_date.strftime("%Y-%m"),
        }
        records.append(record)

    return records


def _to_int(value) -> int:
    """数値文字列を整数に変換（カンマ・空白・単位除去）"""
    if value is None:
        return 0
    try:
        cleaned = str(value).replace(",", "").replace(" ", "").replace("\u3000", "").replace("千円", "").strip()
        return int(float(cleaned)) if cleaned else 0
    except (ValueError, TypeError):
        return 0


def save_to_db(records: list) -> int:
    """
    取得したレコードを WorkRecord テーブルに保存
    同日・同スタッフ・同業務名の重複は上書き

    Returns:
        保存件数
    """
    from app.models import WorkRecord
    from app import db

    saved = 0
    for rec in records:
        if not rec.get("staff_name") or not rec.get("work_date"):
            continue

        existing = WorkRecord.query.filter_by(
            work_date=rec["work_date"],
            staff_name=rec["staff_name"],
            work_name=rec.get("work_name", ""),
        ).first()

        if existing:
            for key, val in rec.items():
                setattr(existing, key, val)
        else:
            obj = WorkRecord(**rec)
            db.session.add(obj)
        saved += 1

    db.session.commit()
    logger.info(f"DB保存完了: {saved}件")
    return saved


def scrape_and_save(target_date: date = None) -> dict:
    """
    スクレイピング → DB保存を一括実行

    Returns:
        {"date": "YYYY-MM-DD", "fetched": N, "saved": N, "error": None or str}
    """
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    result = {"date": target_date.isoformat(), "fetched": 0, "saved": 0, "error": None}
    try:
        records = scrape_daily_csv(target_date)
        result["fetched"] = len(records)
        result["saved"] = save_to_db(records)
    except Exception as e:
        logger.exception("スクレイピングエラー")
        result["error"] = str(e)

    return result
