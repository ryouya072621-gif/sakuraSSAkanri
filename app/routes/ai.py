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
    context = {
        'summary': _get_summary_data(filters),
        'ranking': _get_ranking_data(filters, limit=5),
        'categories': [c.name for c in DisplayCategory.query.all()]
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
        return jsonify({
            'error': 'AI機能が一時的に利用できません',
            'answer': '申し訳ありません。現在AI機能が利用できません。しばらくしてから再度お試しください。'
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
    # 簡略化: 週次データを返す
    return {'message': 'Trend data placeholder'}


def _get_alerts_data(params: dict) -> list:
    """アラートデータを取得"""
    return []


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
