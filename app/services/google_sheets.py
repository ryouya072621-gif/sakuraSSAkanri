"""
Google Sheets API サービス

月次報告書をGoogle Sheetsから自動取得し、DBに保存する。
"""

import os
import re
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from flask import current_app

logger = logging.getLogger(__name__)


def get_sheets_service():
    """Google Sheets APIサービスを取得

    認証方式の優先順:
    1. GOOGLE_API_KEY（APIキー） - 簡単、公開/共有シート向け
    2. GOOGLE_CREDENTIALS_PATH（サービスアカウント） - 非公開シート向け
    """
    try:
        from googleapiclient.discovery import build

        # 方式1: APIキー認証（推奨・簡単）
        api_key = current_app.config.get('GOOGLE_API_KEY')
        if api_key:
            logger.info('Using Google API Key authentication')
            service = build('sheets', 'v4', developerKey=api_key)
            return service

        # 方式2: サービスアカウント認証（フォールバック）
        from google.oauth2 import service_account

        creds_path = current_app.config.get('GOOGLE_CREDENTIALS_PATH', 'credentials.json')
        scopes = current_app.config.get('GOOGLE_SHEETS_SCOPES',
                                         ['https://www.googleapis.com/auth/spreadsheets.readonly'])

        if not os.path.exists(creds_path):
            raise FileNotFoundError(
                'Google認証が設定されていません。\n'
                '.envファイルにGOOGLE_API_KEYを設定するか、\n'
                'credentials.json（サービスアカウント）を配置してください。'
            )

        credentials = service_account.Credentials.from_service_account_file(
            creds_path, scopes=scopes
        )
        service = build('sheets', 'v4', credentials=credentials)
        return service
    except ImportError:
        raise ImportError(
            'Google API packages not installed. Run: '
            'pip install google-api-python-client google-auth'
        )


def extract_spreadsheet_id(url: str) -> Optional[str]:
    """Google SheetsのURLからspreadsheet_idを抽出"""
    patterns = [
        r'/spreadsheets/d/([a-zA-Z0-9_-]+)',
        r'key=([a-zA-Z0-9_-]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_sheet_tabs(service, spreadsheet_id: str) -> List[str]:
    """スプレッドシートのシートタブ一覧を取得"""
    try:
        spreadsheet = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id
        ).execute()
        return [sheet['properties']['title'] for sheet in spreadsheet.get('sheets', [])]
    except Exception as e:
        logger.error(f'Failed to get sheet tabs for {spreadsheet_id}: {e}')
        raise


def get_sheet_data(service, spreadsheet_id: str, sheet_name: str) -> List[List[str]]:
    """特定のシートの全データを取得"""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'",
            valueRenderOption='UNFORMATTED_VALUE'
        ).execute()
        return result.get('values', [])
    except Exception as e:
        logger.error(f'Failed to get data from {spreadsheet_id}/{sheet_name}: {e}')
        raise


def parse_progress_value(value) -> int:
    """進捗率の値をパース（様々な表記に対応）"""
    if value is None or value == '':
        return 0
    if isinstance(value, (int, float)):
        # 0.7 のような小数 → 70%
        if 0 < value < 1:
            return int(value * 100)
        return int(value)
    # 文字列の場合
    text = str(value).strip().replace('%', '').replace('％', '')
    try:
        num = float(text)
        if 0 < num < 1:
            return int(num * 100)
        return int(num)
    except (ValueError, TypeError):
        return 0


def is_year_month_tab(tab_name: str) -> bool:
    """タブ名が年月コード（YYMM形式）かどうか判定"""
    if not tab_name or len(tab_name) != 4:
        return False
    try:
        yy = int(tab_name[:2])
        mm = int(tab_name[2:])
        return 20 <= yy <= 30 and 1 <= mm <= 12
    except ValueError:
        return False


def parse_monthly_report(rows: List[List[str]], sheet_name: str) -> Dict[str, Any]:
    """月次報告書の1シートをパースして構造化データにする

    月次報告書のフォーマット:
    - ヘッダー部: 部門名、報告者名、提出日
    - 目標項目セクション: 目標名 + 進捗率
    - 業務項目セクション: 業務内容
    """
    result = {
        'year_month': sheet_name,
        'goals': [],
        'business_items': [],
        'reporter': '',
        'submission_date': '',
    }

    if not rows or len(rows) < 3:
        return result

    # セクション位置を検出
    goal_section_start = None
    biz_section_start = None

    for i, row in enumerate(rows):
        row_text = ' '.join(str(cell) for cell in row if cell).lower()

        # 目標項目セクション検出
        if any(kw in row_text for kw in ['目標項目', '部門目標', '評価項目', 'mbo']):
            goal_section_start = i
        # 業務項目セクション検出
        elif any(kw in row_text for kw in ['業務項目', '通常業務', '定常業務']):
            biz_section_start = i
        # 報告者検出
        elif any(kw in row_text for kw in ['報告者', '作成者', '記入者']):
            for cell in row:
                cell_str = str(cell).strip()
                if cell_str and cell_str not in ['報告者', '作成者', '記入者', '：', ':']:
                    result['reporter'] = cell_str
                    break

    # 目標項目をパース
    if goal_section_start is not None:
        end = biz_section_start if biz_section_start else min(goal_section_start + 20, len(rows))
        goal_idx = 0
        for i in range(goal_section_start + 1, end):
            if i >= len(rows):
                break
            row = rows[i]
            if not row or not any(str(cell).strip() for cell in row):
                continue

            # 目標名を探す（最初の空でないセル）
            goal_name = ''
            progress = 0
            details = ''

            for j, cell in enumerate(row):
                cell_str = str(cell).strip() if cell else ''
                if not cell_str:
                    continue

                # 進捗率っぽい値を検出
                if isinstance(cell, (int, float)) and (0 <= cell <= 100 or 0 < cell < 1):
                    progress = parse_progress_value(cell)
                elif re.match(r'^\d+%?$', cell_str):
                    progress = parse_progress_value(cell_str)
                elif not goal_name and len(cell_str) > 2:
                    goal_name = cell_str

            # 詳細テキスト（次の行や右側のセルから取得）
            if i + 1 < len(rows) and len(rows[i + 1]) > 0:
                detail_row = rows[i + 1]
                detail_texts = [str(c).strip() for c in detail_row if c and str(c).strip()]
                if detail_texts and len(detail_texts[0]) > 5:
                    details = detail_texts[0]

            if goal_name:
                goal_idx += 1
                result['goals'].append({
                    'goal_index': goal_idx,
                    'goal_name': goal_name,
                    'progress_pct': progress,
                    'details': details,
                })

            if goal_idx >= 5:
                break

    # 業務項目をパース
    if biz_section_start is not None:
        item_idx = 0
        for i in range(biz_section_start + 1, min(biz_section_start + 20, len(rows))):
            if i >= len(rows):
                break
            row = rows[i]
            if not row or not any(str(cell).strip() for cell in row):
                continue

            item_name = ''
            details = ''

            for cell in row:
                cell_str = str(cell).strip() if cell else ''
                if cell_str and len(cell_str) > 2 and not item_name:
                    item_name = cell_str
                    break

            if i + 1 < len(rows) and len(rows[i + 1]) > 0:
                detail_row = rows[i + 1]
                detail_texts = [str(c).strip() for c in detail_row if c and str(c).strip()]
                if detail_texts and len(detail_texts[0]) > 5:
                    details = detail_texts[0]

            if item_name:
                item_idx += 1
                result['business_items'].append({
                    'item_index': item_idx,
                    'item_name': item_name,
                    'details': details,
                })

            if item_idx >= 5:
                break

    return result


def fetch_and_save_sheet(spreadsheet_id: str, department_name: str,
                          staff_name: str = None, year_months: List[str] = None) -> Dict[str, Any]:
    """スプレッドシートからデータを取得してDBに保存

    Args:
        spreadsheet_id: Google SpreadsheetのID
        department_name: 部門名
        staff_name: スタッフ名（None=SV）
        year_months: 取得対象の年月リスト（None=全タブ）

    Returns:
        取得結果のサマリー
    """
    from app import db
    from app.models import MonthlyGoal, MonthlyBusinessItem, DepartmentSheet

    service = get_sheets_service()
    tabs = get_sheet_tabs(service, spreadsheet_id)

    # 年月タブのみフィルタ
    ym_tabs = [t for t in tabs if is_year_month_tab(t)]
    if year_months:
        ym_tabs = [t for t in ym_tabs if t in year_months]

    results = {
        'spreadsheet_id': spreadsheet_id,
        'department': department_name,
        'staff': staff_name,
        'tabs_found': len(ym_tabs),
        'goals_saved': 0,
        'items_saved': 0,
        'errors': [],
    }

    for tab in ym_tabs:
        try:
            rows = get_sheet_data(service, spreadsheet_id, tab)
            parsed = parse_monthly_report(rows, tab)

            # 目標を保存（UPSERT）
            for goal_data in parsed['goals']:
                existing = MonthlyGoal.query.filter_by(
                    department_name=department_name,
                    staff_name=staff_name or '',
                    year_month=tab,
                    goal_index=goal_data['goal_index']
                ).first()

                if existing:
                    existing.goal_name = goal_data['goal_name']
                    existing.progress_pct = goal_data['progress_pct']
                    existing.details = goal_data['details']
                    existing.fetched_at = datetime.utcnow()
                else:
                    goal = MonthlyGoal(
                        department_name=department_name,
                        staff_name=staff_name or '',
                        year_month=tab,
                        goal_index=goal_data['goal_index'],
                        goal_name=goal_data['goal_name'],
                        progress_pct=goal_data['progress_pct'],
                        details=goal_data['details'],
                    )
                    db.session.add(goal)
                results['goals_saved'] += 1

            # 業務項目を保存（UPSERT）
            for item_data in parsed['business_items']:
                existing = MonthlyBusinessItem.query.filter_by(
                    department_name=department_name,
                    staff_name=staff_name or '',
                    year_month=tab,
                    item_index=item_data['item_index']
                ).first()

                if existing:
                    existing.item_name = item_data['item_name']
                    existing.details = item_data['details']
                    existing.fetched_at = datetime.utcnow()
                else:
                    item = MonthlyBusinessItem(
                        department_name=department_name,
                        staff_name=staff_name or '',
                        year_month=tab,
                        item_index=item_data['item_index'],
                        item_name=item_data['item_name'],
                        details=item_data['details'],
                    )
                    db.session.add(item)
                results['items_saved'] += 1

            db.session.commit()

        except Exception as e:
            logger.error(f'Error processing tab {tab}: {e}')
            results['errors'].append(f'{tab}: {str(e)}')
            db.session.rollback()

    # DepartmentSheetの最終取得日時を更新
    sheet = DepartmentSheet.query.filter_by(
        spreadsheet_id=spreadsheet_id,
        department_name=department_name,
        staff_name=staff_name or ''
    ).first()
    if sheet:
        sheet.last_fetched_at = datetime.utcnow()
        sheet.last_error = '; '.join(results['errors']) if results['errors'] else None
        db.session.commit()

    return results


def fetch_all_sheets() -> List[Dict[str, Any]]:
    """全アクティブシートからデータを取得"""
    from app.models import DepartmentSheet

    sheets = DepartmentSheet.query.filter_by(is_active=True).all()
    all_results = []

    for sheet in sheets:
        try:
            result = fetch_and_save_sheet(
                spreadsheet_id=sheet.spreadsheet_id,
                department_name=sheet.department_name,
                staff_name=sheet.staff_name,
            )
            all_results.append(result)
        except Exception as e:
            logger.error(f'Error fetching sheet {sheet.id}: {e}')
            sheet.last_error = str(e)
            sheet.last_fetched_at = datetime.utcnow()
            from app import db
            db.session.commit()
            all_results.append({
                'spreadsheet_id': sheet.spreadsheet_id,
                'department': sheet.department_name,
                'error': str(e),
            })

    return all_results
