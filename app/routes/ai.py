"""
AI API Routes

AI機能のAPIエンドポイント:
- カテゴリ自動分類
- インサイト生成
- チャット
- レポート生成
"""

import hashlib
import json
import logging
from datetime import datetime
from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import func

from app import db
from app.models import (
    WorkRecord, DisplayCategory, CategoryKeyword, CategoryMapping,
    AICategorySuggestion, AIInsightCache, AIRequestLog, AppSetting
)
from app.services import get_ai_provider
from app.services.ai_base import AIProviderError

logger = logging.getLogger(__name__)

bp = Blueprint('ai', __name__, url_prefix='/api/ai')


# ============================================
# カテゴリ分類エンドポイント
# ============================================

@bp.route('/categorize/preview', methods=['POST'])
def preview_categorization():
    """
    業務データのカテゴリ分類プレビュー

    Request body:
    {
        "items": [
            {"category1": "...", "category2": "...", "work_name": "..."},
            ...
        ]
    }

    Response:
    {
        "suggestions": [
            {
                "item_index": 0,
                "original": {...},
                "suggested_category": "...",
                "suggested_category_id": 1,
                "confidence": 0.85,
                "reasoning": "..."
            },
            ...
        ]
    }
    """
    data = request.get_json()
    items = data.get('items', [])

    if not items:
        return jsonify({'error': 'No items provided'}), 400

    max_batch = current_app.config.get('AI_MAX_BATCH_SIZE', 100)
    if len(items) > max_batch:
        return jsonify({'error': f'Maximum {max_batch} items per batch'}), 400

    # カテゴリと既存ルールを取得
    categories = DisplayCategory.query.order_by(DisplayCategory.sort_order).all()
    category_names = [c.name for c in categories]
    category_map = {c.name: c.id for c in categories}

    keywords = CategoryKeyword.query.filter_by(is_active=True).limit(50).all()
    existing_rules = [
        {'keyword': kw.keyword, 'category': kw.display_category.name}
        for kw in keywords
    ]

    try:
        provider = get_ai_provider()
        results = provider.categorize_work_items(items, category_names, existing_rules)

        suggestions = []
        for i, result in enumerate(results):
            item = items[i] if i < len(items) else {}
            suggestions.append({
                'item_index': i,
                'original': item,
                'suggested_category': result.category_name,
                'suggested_category_id': category_map.get(result.category_name),
                'confidence': result.confidence,
                'reasoning': result.reasoning
            })

        return jsonify({'suggestions': suggestions})

    except AIProviderError as e:
        logger.error(f'AI categorization error: {e}')
        # フォールバック: キーワードベースで分類
        fallback_suggestions = []
        for i, item in enumerate(items):
            cat = CategoryMapping.auto_categorize(
                item.get('category2', ''),
                item.get('work_name', '')
            )
            fallback_suggestions.append({
                'item_index': i,
                'original': item,
                'suggested_category': cat,
                'suggested_category_id': category_map.get(cat),
                'confidence': 0.5,
                'reasoning': 'キーワードベースで分類（AI利用不可）'
            })
        return jsonify({
            'suggestions': fallback_suggestions,
            'fallback': True,
            'message': 'AI機能が利用できないため、キーワードベースで分類しました'
        })


@bp.route('/categorize/group-tasks', methods=['POST'])
def group_similar_tasks():
    """
    類似タスクをローカル正規表現でグループ化（高速・APIなし）

    Request body:
    {
        "work_names": ["タスクA", "タスクB", ...],
        "use_ai": false  # オプション: trueならAIで追加処理
    }

    Response:
    {
        "groups": [
            {
                "representative": "代表名",
                "members": ["タスクA", "タスクB"]
            }
        ],
        "original_count": 9527,
        "grouped_count": 800,
        "method": "local"  # "local" or "ai"
    }
    """
    from app.services.task_grouper import local_group_tasks

    data = request.get_json()
    work_names = data.get('work_names', [])
    use_ai = data.get('use_ai', False)

    if not work_names:
        return jsonify({'error': 'No work_names provided'}), 400

    # ローカルグルーピング（高速）
    result = local_group_tasks(work_names, apply_merge=True)

    # オプション: AIで追加処理（グループ数がまだ多い場合）
    if use_ai and result['grouped_count'] > 300:
        max_batch = current_app.config.get('AI_MAX_BATCH_SIZE', 500)
        representatives = [g['representative'] for g in result['groups']]

        if len(representatives) <= max_batch:
            try:
                provider = get_ai_provider()
                ai_result = provider.group_similar_tasks(representatives)

                # AIの結果で再マッピング
                ai_groups = {}
                for g in ai_result.groups:
                    for member in g.members:
                        ai_groups[member] = g.representative

                # ローカルグループをAIグループにマージ
                merged_groups = {}
                for local_group in result['groups']:
                    local_rep = local_group['representative']
                    ai_rep = ai_groups.get(local_rep, local_rep)
                    if ai_rep not in merged_groups:
                        merged_groups[ai_rep] = []
                    merged_groups[ai_rep].extend(local_group['members'])

                result = {
                    'groups': [
                        {'representative': rep, 'members': sorted(set(members))}
                        for rep, members in merged_groups.items()
                    ],
                    'original_count': result['original_count'],
                    'grouped_count': len(merged_groups),
                    'method': 'ai'
                }

            except AIProviderError as e:
                logger.warning(f'AI grouping failed, using local result: {e}')
                result['method'] = 'local'
        else:
            result['method'] = 'local'
    else:
        result['method'] = 'local'

    return jsonify(result)


@bp.route('/categorize/unique-combinations')
def get_unique_combinations():
    """
    データベース内のユニークなcategory1+category2+work_name組み合わせを取得

    Response:
    {
        "combinations": [
            {"category1": "...", "category2": "...", "work_name": "...", "count": 10},
            ...
        ],
        "total": 50
    }
    """
    query = db.session.query(
        WorkRecord.category1,
        WorkRecord.category2,
        WorkRecord.work_name,
        func.count(WorkRecord.id).label('count')
    ).group_by(
        WorkRecord.category1,
        WorkRecord.category2,
        WorkRecord.work_name
    ).order_by(func.count(WorkRecord.id).desc()).limit(200)

    results = query.all()

    combinations = [
        {
            'category1': r.category1 or '',
            'category2': r.category2 or '',
            'work_name': r.work_name or '',
            'count': r.count
        }
        for r in results
    ]

    return jsonify({
        'combinations': combinations,
        'total': len(combinations)
    })


# ============================================
# インサイト生成エンドポイント
# ============================================

@bp.route('/insights')
def get_insights():
    """
    AIインサイトを取得

    Query params: category1, staff, start, end

    Response:
    {
        "highlights": ["..."],
        "concerns": ["..."],
        "recommendations": ["..."],
        "generated_at": "2025-01-01T00:00:00",
        "cached": true/false
    }
    """
    params = {
        'category1': request.args.get('category1'),
        'staff': request.args.get('staff'),
        'start': request.args.get('start'),
        'end': request.args.get('end')
    }

    # キャッシュキー生成
    cache_key = _generate_cache_key('insight', params)

    # キャッシュをチェック
    cached = AIInsightCache.get_cached(cache_key)
    if cached:
        cached['cached'] = True
        return jsonify(cached)

    # データを収集
    summary_data = _get_summary_data(params)
    trend_data = _get_trend_data(params)
    alerts_data = _get_alerts_data(params)

    period = f"{params.get('start', '開始日')} ~ {params.get('end', '終了日')}"

    try:
        provider = get_ai_provider()
        result = provider.generate_insights(summary_data, trend_data, alerts_data, period)

        response_data = {
            'highlights': result.highlights,
            'concerns': result.concerns,
            'recommendations': result.recommendations,
            'generated_at': datetime.utcnow().isoformat(),
            'cached': False
        }

        # キャッシュに保存
        cache_hours = current_app.config.get('AI_INSIGHT_CACHE_HOURS', 1)
        AIInsightCache.set_cache(cache_key, 'dashboard', response_data, cache_hours)

        return jsonify(response_data)

    except AIProviderError as e:
        logger.error(f'Insight generation error: {e}')
        return jsonify({
            'error': 'AI機能が一時的に利用できません',
            'highlights': [],
            'concerns': [],
            'recommendations': []
        }), 503


# ============================================
# チャットエンドポイント
# ============================================

@bp.route('/chat', methods=['POST'])
def chat():
    """
    自然言語質問に回答

    Request body:
    {
        "question": "今週一番時間を使った業務は？",
        "history": [{"user": "...", "assistant": "..."}, ...],
        "filters": {"category1": "...", "staff": "...", ...}
    }

    Response:
    {
        "answer": "...",
        "data_references": [...],
        "follow_up_questions": [...]
    }
    """
    data = request.get_json()
    question = data.get('question', '').strip()
    history = data.get('history', [])
    filters = data.get('filters', {})

    if not question:
        return jsonify({'error': 'Question required'}), 400

    # コンテキストデータを構築
    trend_data = _get_trend_data(filters)
    context = {
        'staff_name': filters.get('staff', '全スタッフ'),
        'department': filters.get('category1', '全部門'),
        'period': f"{filters.get('start', '開始日')} ~ {filters.get('end', '終了日')}",
        'summary': _get_summary_data(filters),
        'ranking': _get_ranking_data(filters, limit=20),
        'category_breakdown': _get_category_breakdown(filters),
        'trend_statistics': trend_data.get('statistics', {}),
        'weekly_trend': _get_weekly_trend(filters),
        'staff_summary': _get_staff_summary(filters),
        'reduction_analysis': _get_reduction_analysis(filters),
        'available_categories': [c.name for c in DisplayCategory.query.all()]
    }

    try:
        provider = get_ai_provider()
        response = provider.chat_query(question, context, history)

        return jsonify({
            'answer': response.answer,
            'data_references': response.data_references,
            'follow_up_questions': response.follow_up_questions
        })

    except AIProviderError as e:
        logger.error(f'Chat error: {e}')
        print(f'[AI ERROR] {e}')  # コンソールにも出力
        return jsonify({
            'error': 'AI機能が一時的に利用できません',
            'answer': f'エラー: {str(e)}'
        }), 503
    except Exception as e:
        logger.error(f'Unexpected chat error: {e}')
        print(f'[UNEXPECTED ERROR] {e}')  # コンソールにも出力
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': 'AI機能が一時的に利用できません',
            'answer': f'予期しないエラー: {str(e)}'
        }), 503


# ============================================
# レポート生成エンドポイント
# ============================================

@bp.route('/report', methods=['POST'])
def generate_report():
    """
    レポートを生成

    Request body:
    {
        "type": "weekly" or "monthly",
        "filters": {...}
    }

    Response:
    {
        "report": "# Markdown content...",
        "format": "markdown",
        "generated_at": "2025-01-01T00:00:00"
    }
    """
    data = request.get_json()
    report_type = data.get('type', 'weekly')
    filters = data.get('filters', {})

    # レポート用データを収集
    report_data = {
        'summary': _get_summary_data(filters),
        'trend': _get_trend_data(filters),
        'ranking': _get_ranking_data(filters, limit=10)
    }

    period_start = filters.get('start', '')
    period_end = filters.get('end', '')

    try:
        provider = get_ai_provider()
        result = provider.generate_report(report_type, report_data, period_start, period_end)

        return jsonify({
            'report': result.content,
            'format': result.format,
            'generated_at': datetime.utcnow().isoformat()
        })

    except AIProviderError as e:
        logger.error(f'Report generation error: {e}')
        return jsonify({'error': 'AI機能が一時的に利用できません'}), 503


# ============================================
# ヘルパー関数
# ============================================

def _generate_cache_key(prefix: str, params: dict) -> str:
    """キャッシュキーを生成"""
    param_str = json.dumps(params, sort_keys=True)
    hash_str = hashlib.md5(param_str.encode()).hexdigest()[:16]
    return f"{prefix}:{hash_str}"


def _get_summary_data(params: dict) -> dict:
    """サマリーデータを取得"""
    query = db.session.query(
        func.sum(WorkRecord.quantity).label('total_hours'),
        func.count(func.distinct(WorkRecord.work_name)).label('task_types')
    )

    if params.get('category1'):
        query = query.filter(WorkRecord.category1 == params['category1'])
    if params.get('staff'):
        query = query.filter(WorkRecord.staff_name == params['staff'])
    if params.get('start'):
        query = query.filter(WorkRecord.work_date >= datetime.strptime(params['start'], '%Y-%m-%d').date())
    if params.get('end'):
        query = query.filter(WorkRecord.work_date <= datetime.strptime(params['end'], '%Y-%m-%d').date())

    result = query.first()
    total_hours = result.total_hours or 0
    task_types = result.task_types or 0

    hourly_rate = int(params.get('hourly_rate', 2000) or 2000)
    total_cost = total_hours * hourly_rate

    return {
        'total_hours': round(total_hours, 1),
        'total_cost': int(total_cost),
        'task_types': task_types,
        'reduction_ratio': 0  # 簡略化
    }


def _get_trend_data(params: dict) -> dict:
    """推移データを取得"""
    query = db.session.query(
        WorkRecord.work_date,
        func.sum(WorkRecord.quantity).label('hours')
    )

    if params.get('category1'):
        query = query.filter(WorkRecord.category1 == params['category1'])
    if params.get('staff'):
        query = query.filter(WorkRecord.staff_name == params['staff'])
    if params.get('start'):
        query = query.filter(WorkRecord.work_date >= datetime.strptime(params['start'], '%Y-%m-%d').date())
    if params.get('end'):
        query = query.filter(WorkRecord.work_date <= datetime.strptime(params['end'], '%Y-%m-%d').date())

    results = query.group_by(WorkRecord.work_date).order_by(WorkRecord.work_date).all()

    daily_data = [
        {'date': r.work_date.strftime('%Y-%m-%d'), 'hours': round(r.hours, 1)}
        for r in results
    ]

    # 統計情報も計算
    if daily_data:
        hours_list = [d['hours'] for d in daily_data]
        avg_hours = sum(hours_list) / len(hours_list)
        max_hours = max(hours_list)
        min_hours = min(hours_list)
    else:
        avg_hours = max_hours = min_hours = 0

    return {
        'daily': daily_data,
        'statistics': {
            'average_daily_hours': round(avg_hours, 1),
            'max_daily_hours': round(max_hours, 1),
            'min_daily_hours': round(min_hours, 1),
            'working_days': len(daily_data)
        }
    }


def _get_alerts_data(params: dict) -> list:
    """アラートデータを取得"""
    alerts = []

    # カテゴリ別の時間を取得
    query = db.session.query(
        WorkRecord.category2,
        WorkRecord.work_name,
        func.sum(WorkRecord.quantity).label('hours')
    )

    if params.get('category1'):
        query = query.filter(WorkRecord.category1 == params['category1'])
    if params.get('staff'):
        query = query.filter(WorkRecord.staff_name == params['staff'])
    if params.get('start'):
        query = query.filter(WorkRecord.work_date >= datetime.strptime(params['start'], '%Y-%m-%d').date())
    if params.get('end'):
        query = query.filter(WorkRecord.work_date <= datetime.strptime(params['end'], '%Y-%m-%d').date())

    results = query.group_by(WorkRecord.category2, WorkRecord.work_name).all()

    # 表示カテゴリごとに集計
    category_hours = {}
    for cat2, work_name, hours in results:
        display_cat = CategoryMapping.auto_categorize(cat2, work_name)
        category_hours[display_cat] = category_hours.get(display_cat, 0) + (hours or 0)

    total_hours = sum(category_hours.values())
    if total_hours > 0:
        for category, hours in category_hours.items():
            ratio = (hours / total_hours) * 100

            # 「その他」や「不明」が多い場合にアラート
            if category in ['その他', '不明', 'その他・不明'] and ratio > 20:
                alerts.append({
                    'type': 'warning',
                    'message': f'「{category}」が{ratio:.1f}%を占めています。カテゴリ分類の見直しを検討してください。'
                })

            # 特定カテゴリが極端に多い場合
            if ratio > 50:
                alerts.append({
                    'type': 'info',
                    'message': f'「{category}」が業務時間の{ratio:.1f}%を占めています。'
                })

    return alerts


def _get_ranking_data(params: dict, limit: int = 10) -> list:
    """ランキングデータを取得"""
    query = db.session.query(
        WorkRecord.work_name,
        WorkRecord.category2,
        func.sum(WorkRecord.quantity).label('hours')
    )

    if params.get('category1'):
        query = query.filter(WorkRecord.category1 == params['category1'])
    if params.get('staff'):
        query = query.filter(WorkRecord.staff_name == params['staff'])
    if params.get('start'):
        query = query.filter(WorkRecord.work_date >= datetime.strptime(params['start'], '%Y-%m-%d').date())
    if params.get('end'):
        query = query.filter(WorkRecord.work_date <= datetime.strptime(params['end'], '%Y-%m-%d').date())

    results = query.group_by(
        WorkRecord.work_name,
        WorkRecord.category2
    ).order_by(func.sum(WorkRecord.quantity).desc()).limit(limit).all()

    return [
        {
            'work_name': r.work_name,
            'category2': r.category2,
            'hours': round(r.hours, 1)
        }
        for r in results
    ]


def _get_category_breakdown(params: dict) -> list:
    """カテゴリ別時間内訳を取得"""
    query = db.session.query(
        WorkRecord.category2,
        WorkRecord.work_name,
        func.sum(WorkRecord.quantity).label('hours')
    )

    if params.get('category1'):
        query = query.filter(WorkRecord.category1 == params['category1'])
    if params.get('staff'):
        query = query.filter(WorkRecord.staff_name == params['staff'])
    if params.get('start'):
        query = query.filter(WorkRecord.work_date >= datetime.strptime(params['start'], '%Y-%m-%d').date())
    if params.get('end'):
        query = query.filter(WorkRecord.work_date <= datetime.strptime(params['end'], '%Y-%m-%d').date())

    results = query.group_by(WorkRecord.category2, WorkRecord.work_name).all()

    # 表示カテゴリごとに集計
    category_hours = {}
    for cat2, work_name, hours in results:
        display_cat = CategoryMapping.auto_categorize(cat2, work_name)
        category_hours[display_cat] = category_hours.get(display_cat, 0) + (hours or 0)

    total_hours = sum(category_hours.values())

    # 時間順にソート
    sorted_categories = sorted(category_hours.items(), key=lambda x: x[1], reverse=True)

    return [
        {
            'category': cat,
            'hours': round(hours, 1),
            'percentage': round(hours / total_hours * 100, 1) if total_hours > 0 else 0
        }
        for cat, hours in sorted_categories
    ]


def _get_weekly_trend(params: dict) -> list:
    """週次トレンドデータを取得"""
    from datetime import timedelta

    query = db.session.query(
        WorkRecord.work_date,
        WorkRecord.category2,
        WorkRecord.work_name,
        func.sum(WorkRecord.quantity).label('hours')
    )

    if params.get('category1'):
        query = query.filter(WorkRecord.category1 == params['category1'])
    if params.get('staff'):
        query = query.filter(WorkRecord.staff_name == params['staff'])
    if params.get('start'):
        query = query.filter(WorkRecord.work_date >= datetime.strptime(params['start'], '%Y-%m-%d').date())
    if params.get('end'):
        query = query.filter(WorkRecord.work_date <= datetime.strptime(params['end'], '%Y-%m-%d').date())

    results = query.group_by(WorkRecord.work_date, WorkRecord.category2, WorkRecord.work_name).all()

    # 週ごとに集計
    weekly_data = {}
    for work_date, cat2, work_name, hours in results:
        # 週の開始日（月曜日）を計算
        week_start = work_date - timedelta(days=work_date.weekday())
        week_key = week_start.strftime('%Y-%m-%d')

        if week_key not in weekly_data:
            weekly_data[week_key] = {'total': 0, 'categories': {}}

        display_cat = CategoryMapping.auto_categorize(cat2, work_name)
        weekly_data[week_key]['total'] += hours or 0
        weekly_data[week_key]['categories'][display_cat] = weekly_data[week_key]['categories'].get(display_cat, 0) + (hours or 0)

    # 直近8週間のみ返す
    sorted_weeks = sorted(weekly_data.keys(), reverse=True)[:8]
    return [
        {
            'week': week,
            'total_hours': round(weekly_data[week]['total'], 1),
            'top_category': max(weekly_data[week]['categories'].items(), key=lambda x: x[1])[0] if weekly_data[week]['categories'] else None
        }
        for week in reversed(sorted_weeks)
    ]


def _get_staff_summary(params: dict) -> list:
    """スタッフ別サマリーを取得"""
    query = db.session.query(
        WorkRecord.staff_name,
        WorkRecord.category2,
        WorkRecord.work_name,
        func.sum(WorkRecord.quantity).label('hours')
    )

    if params.get('category1'):
        query = query.filter(WorkRecord.category1 == params['category1'])
    if params.get('start'):
        query = query.filter(WorkRecord.work_date >= datetime.strptime(params['start'], '%Y-%m-%d').date())
    if params.get('end'):
        query = query.filter(WorkRecord.work_date <= datetime.strptime(params['end'], '%Y-%m-%d').date())

    results = query.group_by(WorkRecord.staff_name, WorkRecord.category2, WorkRecord.work_name).all()

    # スタッフごとに集計
    staff_data = {}
    for staff_name, cat2, work_name, hours in results:
        if not staff_name:
            continue
        if staff_name not in staff_data:
            staff_data[staff_name] = {'total': 0, 'core': 0, 'other': 0}

        display_cat = CategoryMapping.auto_categorize(cat2, work_name)
        staff_data[staff_name]['total'] += hours or 0
        if display_cat == 'コア業務':
            staff_data[staff_name]['core'] += hours or 0
        else:
            staff_data[staff_name]['other'] += hours or 0

    # 上位10名のみ返す
    sorted_staff = sorted(staff_data.items(), key=lambda x: x[1]['total'], reverse=True)[:10]
    return [
        {
            'name': name,
            'total_hours': round(data['total'], 1),
            'core_ratio': round(data['core'] / data['total'] * 100, 1) if data['total'] > 0 else 0
        }
        for name, data in sorted_staff
    ]


def _get_reduction_analysis(params: dict) -> dict:
    """削減対象業務の分析"""
    from app.models import TaskReductionTarget

    query = db.session.query(
        WorkRecord.category2,
        WorkRecord.work_name,
        func.sum(WorkRecord.quantity).label('hours')
    )

    if params.get('category1'):
        query = query.filter(WorkRecord.category1 == params['category1'])
    if params.get('staff'):
        query = query.filter(WorkRecord.staff_name == params['staff'])
    if params.get('start'):
        query = query.filter(WorkRecord.work_date >= datetime.strptime(params['start'], '%Y-%m-%d').date())
    if params.get('end'):
        query = query.filter(WorkRecord.work_date <= datetime.strptime(params['end'], '%Y-%m-%d').date())

    results = query.group_by(WorkRecord.category2, WorkRecord.work_name).all()

    total_hours = 0
    reduction_hours = 0
    reduction_tasks = []

    for cat2, work_name, hours in results:
        total_hours += hours or 0
        display_cat = CategoryMapping.auto_categorize(cat2, work_name)
        is_category_reduction = CategoryMapping.is_target_for_reduction(display_cat)
        is_task_reduction = TaskReductionTarget.is_work_reduction_target(work_name)

        if is_category_reduction or is_task_reduction:
            reduction_hours += hours or 0
            reduction_tasks.append({
                'work_name': work_name,
                'hours': round(hours or 0, 1),
                'reason': 'カテゴリ対象' if is_category_reduction else '業務名対象'
            })

    # 上位5件のみ
    reduction_tasks = sorted(reduction_tasks, key=lambda x: x['hours'], reverse=True)[:5]

    return {
        'total_hours': round(total_hours, 1),
        'reduction_hours': round(reduction_hours, 1),
        'reduction_ratio': round(reduction_hours / total_hours * 100, 1) if total_hours > 0 else 0,
        'top_reduction_tasks': reduction_tasks
    }
