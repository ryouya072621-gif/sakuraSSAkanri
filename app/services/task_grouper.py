"""
Local Task Grouping Service

正規表現ベースのローカルタスクグルーピング。
AIに送る前の前処理として使用し、API呼び出し回数を大幅に削減する。
"""

import re
from typing import List, Dict, Tuple
from collections import defaultdict


def normalize_work_name(name: str) -> str:
    """
    業務名を正規化して代表名を生成

    正規化ルール:
    1. 括弧内の補足を除去: "施工ノート入力（修正）" → "施工ノート入力"
    2. A/B/C等のサフィックスを除去: "施工ノートA" → "施工ノート"
    3. 番号を除去: "Wチェック業務（1号登録）" → "Wチェック業務"
    4. 略語を統一: "TEL" → "電話", "MTG" → "会議"
    5. 空白を正規化
    """
    if not name:
        return ""

    result = name.strip()

    # 1. 括弧内を除去（全角・半角両方）
    result = re.sub(r'[（(][^)）]*[)）]', '', result)

    # 2. 末尾のA/B/C/D等を除去（スペース有無両方）
    result = re.sub(r'\s*[A-Za-zＡ-Ｚａ-ｚ]$', '', result)

    # 3. 末尾の数字を除去（日付っぽいものは除く）
    result = re.sub(r'\s*\d{1,2}$', '', result)

    # 4. 略語を統一
    abbreviations = {
        'TEL': '電話',
        'tel': '電話',
        'Tel': '電話',
        'MTG': '会議',
        'mtg': '会議',
        'Mtg': '会議',
        'ＴＥＬ': '電話',
        'ＭＴＧ': '会議',
    }
    for abbr, full in abbreviations.items():
        result = result.replace(abbr, full)

    # 5. 空白の正規化
    result = re.sub(r'\s+', ' ', result).strip()

    # 6. 全角英数を半角に（オプション）
    # result = unicodedata.normalize('NFKC', result)

    return result


def group_work_names(work_names: List[str]) -> Dict[str, List[str]]:
    """
    業務名をローカルでグループ化

    Args:
        work_names: 元の業務名リスト

    Returns:
        代表名 → 元の業務名リストのマッピング
    """
    groups = defaultdict(list)

    for name in work_names:
        if not name:
            continue
        normalized = normalize_work_name(name)
        if normalized:
            groups[normalized].append(name)

    return dict(groups)


def group_work_names_with_result(work_names: List[str]) -> Tuple[List[Dict], int, int]:
    """
    業務名をグループ化し、APIレスポンス形式で返す

    Returns:
        (groups, original_count, grouped_count)
        groups: [{"representative": "代表名", "members": ["元の名前1", ...]}, ...]
    """
    unique_names = list(set(work_names))
    original_count = len(unique_names)

    grouped = group_work_names(unique_names)

    groups = [
        {
            "representative": rep,
            "members": members
        }
        for rep, members in grouped.items()
    ]

    # 代表名でソート
    groups.sort(key=lambda x: x["representative"])

    return groups, original_count, len(groups)


# 追加の正規化ルール（必要に応じて拡張）
MERGE_PATTERNS = [
    # (パターン, 統一名)
    (r'.*電話.*対応.*', '電話対応'),
    (r'.*メール.*対応.*', 'メール対応'),
    (r'.*電話.*メール.*', '電話/メール対応'),
    (r'.*移動.*', '移動'),
    (r'.*打ち?合わせ.*', '打ち合わせ'),
    (r'.*ミーティング.*', '会議'),
]


def apply_merge_patterns(groups: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """
    追加のマージパターンを適用して、さらにグループを統合

    例: "電話対応", "電話対応（折り返し）", "TEL対応" → "電話対応"
    """
    merged = defaultdict(list)

    for rep, members in groups.items():
        merged_to = rep
        for pattern, unified_name in MERGE_PATTERNS:
            if re.match(pattern, rep, re.IGNORECASE):
                merged_to = unified_name
                break
        merged[merged_to].extend(members)

    return dict(merged)


# ============================================
# 中分類（業務グループ）抽出
# ============================================

# 末尾キーワードによる中分類マッピング
SUFFIX_TO_GROUP = [
    ('入力', '入力系'),
    ('対応', '対応系'),
    ('作成', '作成系'),
    ('確認', '確認系'),
    ('管理', '管理系'),
    ('チェック', 'チェック系'),
    ('処理', '処理系'),
    ('登録', '登録系'),
    ('発注', '発注系'),
    ('手配', '手配系'),
]

# 含まれるキーワードによる中分類マッピング
CONTAINS_TO_GROUP = [
    ('MTG', 'MTG系'),
    ('ミーティング', 'MTG系'),
    ('会議', 'MTG系'),
    ('打ち合わせ', 'MTG系'),
    ('打合せ', 'MTG系'),
    ('面談', '面談系'),
    ('移動', '移動系'),
    ('キッズ', 'キッズ系'),
    ('研修', '研修系'),
    ('説明会', '説明会系'),
]


def extract_task_group(work_name: str) -> Tuple[str, str]:
    """
    業務名から中分類と正規化名を抽出

    Returns:
        (中分類名, 正規化された業務名)

    Examples:
        "電話対応（折り返し）" → ("対応系", "電話対応")
        "技工物ノート入力" → ("入力系", "技工物ノート入力")
        "マネージャーMTG" → ("MTG系", "MTG")
        "医療法人確認（クローバーからイーアス）" → ("確認系", "医療法人確認")
    """
    if not work_name:
        return ('その他', '')

    # 括弧を除去して正規化
    normalized = re.sub(r'[（(][^)）]*[)）]', '', work_name).strip()

    # 末尾のA/B/C等を除去
    normalized = re.sub(r'\s*[A-Za-zＡ-Ｚａ-ｚ]$', '', normalized).strip()

    # 末尾キーワードで分類（優先度高）
    for suffix, group_name in SUFFIX_TO_GROUP:
        if normalized.endswith(suffix):
            return (group_name, normalized)

    # 含まれるキーワードで分類
    for keyword, group_name in CONTAINS_TO_GROUP:
        if keyword in normalized or keyword in work_name:
            # MTG系は代表名を「MTG」に統一
            if group_name == 'MTG系':
                return (group_name, 'MTG')
            return (group_name, normalized)

    return ('その他', normalized)


def group_ranking_by_task_group(ranking_items: List[Dict]) -> List[Dict]:
    """
    ランキングデータを中分類でグループ化

    Args:
        ranking_items: [{"work_name": "...", "hours": 100, ...}, ...]

    Returns:
        グループ化されたランキング:
        [
            {
                "group_name": "対応系",
                "normalized_name": "電話対応",
                "total_hours": 150,
                "total_cost": 375000,
                "members": [
                    {"work_name": "電話対応", "hours": 100, ...},
                    {"work_name": "電話対応（折り返し）", "hours": 50, ...}
                ],
                "category": "コア業務"
            }
        ]
    """
    from collections import defaultdict

    # 正規化名でグルーピング
    groups = defaultdict(lambda: {
        'members': [],
        'total_hours': 0,
        'total_cost': 0,
        'total_quantity': 0,
        'group_name': '',
        'category': ''
    })

    for item in ranking_items:
        work_name = item.get('work_name', '')
        group_name, normalized = extract_task_group(work_name)

        key = (group_name, normalized)
        groups[key]['members'].append(item)
        groups[key]['total_hours'] += item.get('hours', 0)
        groups[key]['total_cost'] += item.get('cost', 0)
        groups[key]['total_quantity'] += item.get('quantity', 0)
        groups[key]['group_name'] = group_name
        groups[key]['normalized_name'] = normalized

        # カテゴリは最初のアイテムから取得（同じグループは同じカテゴリのはず）
        if not groups[key]['category'] and item.get('category'):
            groups[key]['category'] = item.get('category')

    # 結果を整形
    result = []
    for (group_name, normalized), data in groups.items():
        result.append({
            'group_name': group_name,
            'normalized_name': normalized,
            'total_hours': round(data['total_hours'], 1),
            'total_cost': data['total_cost'],
            'total_quantity': data['total_quantity'],
            'category': data['category'],
            'member_count': len(data['members']),
            'members': sorted(data['members'], key=lambda x: -x.get('hours', 0))
        })

    # 時間の降順でソート
    result.sort(key=lambda x: -x['total_hours'])

    return result


def local_group_tasks(work_names: List[str], apply_merge: bool = False) -> dict:
    """
    メインのローカルグルーピング関数

    Args:
        work_names: 業務名のリスト
        apply_merge: 追加のマージパターンを適用するかどうか

    Returns:
        {
            "groups": [{"representative": "...", "members": [...]}],
            "original_count": 9527,
            "grouped_count": 800
        }
    """
    unique_names = list(set(n for n in work_names if n))
    original_count = len(unique_names)

    if original_count == 0:
        return {
            "groups": [],
            "original_count": 0,
            "grouped_count": 0
        }

    # Step 1: 基本の正規化グルーピング
    grouped = group_work_names(unique_names)

    # Step 2: オプションで追加マージ
    if apply_merge:
        grouped = apply_merge_patterns(grouped)

    # 結果を整形
    groups = [
        {
            "representative": rep,
            "members": sorted(set(members))  # 重複除去してソート
        }
        for rep, members in grouped.items()
    ]

    # 代表名でソート
    groups.sort(key=lambda x: x["representative"])

    return {
        "groups": groups,
        "original_count": original_count,
        "grouped_count": len(groups)
    }


# ============================================
# 単位タイプ判定（時間制 vs 件数制）
# ============================================

# デフォルトの単位タイプルール（DBルールがない場合のフォールバック）
DEFAULT_UNIT_RULES = {
    # 時間制
    'hours': {
        'contains': ['MTG', '会議', 'ミーティング', '打ち合わせ', '打合せ', '面談', '研修', '移動'],
        'suffix': ['対応']
    },
    # 件数制
    'count': {
        'contains': [],
        'suffix': ['入力', '作成', 'チェック', '確認', '処理', '登録', '発注', '手配']
    }
}


def get_unit_type(work_name: str) -> str:
    """
    業務名から単位タイプを判定

    DBにルールがあればそれを使用、なければデフォルトルールを使用

    Returns:
        'hours' - 時間制（1h, 2hなど）
        'count' - 件数制（1件, 2件など）
    """
    if not work_name:
        return 'hours'

    # DBルールを試す（アプリケーションコンテキスト内で呼ばれた場合）
    try:
        from app.models import UnitTypeRule
        return UnitTypeRule.get_unit_type(work_name)
    except (ImportError, RuntimeError):
        # アプリケーションコンテキスト外の場合はデフォルトルールを使用
        pass

    # デフォルトルールで判定
    work_name_lower = work_name.lower()

    # 時間制チェック
    for keyword in DEFAULT_UNIT_RULES['hours']['contains']:
        if keyword.lower() in work_name_lower:
            return 'hours'
    for suffix in DEFAULT_UNIT_RULES['hours']['suffix']:
        if work_name_lower.endswith(suffix.lower()):
            return 'hours'

    # 件数制チェック
    for keyword in DEFAULT_UNIT_RULES['count']['contains']:
        if keyword.lower() in work_name_lower:
            return 'count'
    for suffix in DEFAULT_UNIT_RULES['count']['suffix']:
        if work_name_lower.endswith(suffix.lower()):
            return 'count'

    return 'hours'  # デフォルトは時間制


def get_unit_suffix(work_name: str) -> str:
    """
    業務名から表示用の単位を取得

    Returns:
        'h' - 時間制の場合
        '件' - 件数制の場合
    """
    unit_type = get_unit_type(work_name)
    return 'h' if unit_type == 'hours' else '件'


# ============================================
# サブカテゴリ判定（コア業務の細分化）
# ============================================

# デフォルトのサブカテゴリルール
DEFAULT_SUB_CATEGORY_RULES = [
    # (キーワード, マッチタイプ, サブカテゴリ名)
    ('電話対応', 'contains', '顧客対応系'),
    ('メール対応', 'contains', '顧客対応系'),
    ('TEL対応', 'contains', '顧客対応系'),
    ('対応', 'suffix', '顧客対応系'),

    ('Wチェック', 'contains', '専門作業系'),
    ('レセチェック', 'contains', '専門作業系'),
    ('チェック', 'suffix', '専門作業系'),

    ('ノート作成', 'contains', '制作系'),
    ('書類作成', 'contains', '制作系'),
    ('資料作成', 'contains', '制作系'),
    ('作成', 'suffix', '制作系'),

    ('施工', 'contains', '技術系'),
    ('技工', 'contains', '技術系'),

    ('ノート入力', 'contains', '入力系'),
    ('入力', 'suffix', '入力系'),
]


def get_sub_category(work_name: str, parent_category_id: int = None) -> str:
    """
    業務名からサブカテゴリを判定

    DBにルールがあればそれを使用、なければデフォルトルールを使用

    Returns:
        サブカテゴリ名（見つからない場合はNone）
    """
    if not work_name:
        return None

    # DBルールを試す
    try:
        from app.models import SubCategoryRule
        result = SubCategoryRule.get_sub_category(work_name, parent_category_id)
        if result:
            return result
    except (ImportError, RuntimeError):
        pass

    # デフォルトルールで判定
    work_name_lower = work_name.lower()

    for keyword, match_type, sub_cat in DEFAULT_SUB_CATEGORY_RULES:
        keyword_lower = keyword.lower()
        if match_type == 'contains' and keyword_lower in work_name_lower:
            return sub_cat
        elif match_type == 'suffix' and work_name_lower.endswith(keyword_lower):
            return sub_cat

    return None


def enrich_ranking_with_unit_and_subcategory(ranking_items: List[Dict]) -> List[Dict]:
    """
    ランキングデータに単位タイプとサブカテゴリ情報を追加

    Args:
        ranking_items: [{"work_name": "...", "hours": 100, ...}, ...]

    Returns:
        追加情報付きのランキング:
        [
            {
                "work_name": "電話対応",
                "hours": 100,
                "unit_type": "hours",
                "unit_suffix": "h",
                "sub_category": "顧客対応系",
                ...
            }
        ]
    """
    for item in ranking_items:
        work_name = item.get('work_name', '')
        item['unit_type'] = get_unit_type(work_name)
        item['unit_suffix'] = get_unit_suffix(work_name)
        item['sub_category'] = get_sub_category(work_name)

    return ranking_items
