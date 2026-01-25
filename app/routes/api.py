from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from sqlalchemy import func, distinct
from app import db
from app.models import WorkRecord, CategoryMapping, DisplayCategory, AppSetting

bp = Blueprint('api', __name__, url_prefix='/api')


@bp.route('/categories1')
def get_categories1():
    """大分類（仕事分類1）一覧を取得"""
    cats = db.session.query(
        WorkRecord.category1
    ).distinct().order_by(WorkRecord.category1).all()

    result = [c.category1 for c in cats if c.category1]
    return jsonify(result)


@bp.route('/staff')
def get_staff_list():
    """スタッフ一覧を取得（名前のみ、重複なし）"""
    category1 = request.args.get('category1')

    query = db.session.query(WorkRecord.staff_name).distinct()

    if category1:
        query = query.filter(WorkRecord.category1 == category1)

    staff = query.order_by(WorkRecord.staff_name).all()

    result = [{'name': s.staff_name} for s in staff if s.staff_name]
    return jsonify(result)


@bp.route('/summary')
def get_summary():
    """集計サマリーを取得"""
    category1 = request.args.get('category1')
    staff = request.args.get('staff')
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    default_rate = AppSetting.get_value('default_hourly_rate', 2000)
    hourly_rate = int(request.args.get('hourly_rate', default_rate))

    # SQL集計クエリを使用（全件取得を回避）
    query = db.session.query(
        func.sum(WorkRecord.quantity).label('total_hours'),
        func.sum(WorkRecord.total_amount).label('total_cost'),
        func.count(distinct(WorkRecord.work_name)).label('task_types')
    )

    if category1:
        query = query.filter(WorkRecord.category1 == category1)
    if staff:
        query = query.filter(WorkRecord.staff_name == staff)
    if start_date:
        query = query.filter(WorkRecord.work_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(WorkRecord.work_date <= datetime.strptime(end_date, '%Y-%m-%d').date())

    result = query.first()
    total_hours = result.total_hours or 0
    total_cost = result.total_cost or 0
    task_types = result.task_types or 0

    # 削減対象の計算（category2+work_nameごとに集計してからPythonで処理）
    cat2_query = db.session.query(
        WorkRecord.category2,
        WorkRecord.work_name,
        func.sum(WorkRecord.quantity).label('hours')
    )
    if category1:
        cat2_query = cat2_query.filter(WorkRecord.category1 == category1)
    if staff:
        cat2_query = cat2_query.filter(WorkRecord.staff_name == staff)
    if start_date:
        cat2_query = cat2_query.filter(WorkRecord.work_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        cat2_query = cat2_query.filter(WorkRecord.work_date <= datetime.strptime(end_date, '%Y-%m-%d').date())

    cat2_stats = cat2_query.group_by(WorkRecord.category2, WorkRecord.work_name).all()

    reduction_hours = 0
    for cat2, work_name, hours in cat2_stats:
        display_cat = CategoryMapping.auto_categorize(cat2, work_name)
        if CategoryMapping.is_target_for_reduction(display_cat):
            reduction_hours += hours

    reduction_ratio = (reduction_hours / total_hours * 100) if total_hours > 0 else 0

    return jsonify({
        'total_hours': round(total_hours, 1),
        'total_cost': total_cost,
        'estimated_cost': total_hours * hourly_rate,
        'task_types': task_types,
        'reduction_ratio': round(reduction_ratio, 1)
    })


@bp.route('/category-breakdown')
def get_category_breakdown():
    """カテゴリ別内訳を取得"""
    category1 = request.args.get('category1')
    staff = request.args.get('staff')
    start_date = request.args.get('start')
    end_date = request.args.get('end')

    # category2+work_nameごとにSQL集計
    query = db.session.query(
        WorkRecord.category2,
        WorkRecord.work_name,
        func.sum(WorkRecord.quantity).label('hours')
    )

    if category1:
        query = query.filter(WorkRecord.category1 == category1)
    if staff:
        query = query.filter(WorkRecord.staff_name == staff)
    if start_date:
        query = query.filter(WorkRecord.work_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(WorkRecord.work_date <= datetime.strptime(end_date, '%Y-%m-%d').date())

    cat2_stats = query.group_by(WorkRecord.category2, WorkRecord.work_name).all()

    # 表示カテゴリごとに集計
    category_hours = {}
    for cat2, work_name, hours in cat2_stats:
        display_cat = CategoryMapping.auto_categorize(cat2, work_name)
        category_hours[display_cat] = category_hours.get(display_cat, 0) + hours

    # DBからカテゴリ一覧を取得（順序順）
    db_categories = DisplayCategory.query.order_by(DisplayCategory.sort_order).all()
    categories = [c.name for c in db_categories]

    result = []
    for cat in categories:
        hours = category_hours.get(cat, 0)
        result.append({'category': cat, 'hours': round(hours, 1)})

    return jsonify(result)


@bp.route('/daily-breakdown')
def get_daily_breakdown():
    """日次カテゴリ別内訳を取得"""
    category1 = request.args.get('category1')
    staff = request.args.get('staff')
    start_date = request.args.get('start')
    end_date = request.args.get('end')

    # 日付とcategory2+work_nameごとにSQL集計
    query = db.session.query(
        WorkRecord.work_date,
        WorkRecord.category2,
        WorkRecord.work_name,
        func.sum(WorkRecord.quantity).label('hours')
    )

    if category1:
        query = query.filter(WorkRecord.category1 == category1)
    if staff:
        query = query.filter(WorkRecord.staff_name == staff)
    if start_date:
        query = query.filter(WorkRecord.work_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(WorkRecord.work_date <= datetime.strptime(end_date, '%Y-%m-%d').date())

    daily_stats = query.group_by(WorkRecord.work_date, WorkRecord.category2, WorkRecord.work_name).all()

    # DBからカテゴリ一覧を取得（順序順）
    db_categories = DisplayCategory.query.order_by(DisplayCategory.sort_order).all()
    categories = [c.name for c in db_categories]
    colors = {c.name: c.color for c in db_categories}

    daily_data = {}
    for work_date, cat2, work_name, hours in daily_stats:
        date_str = work_date.strftime('%m-%d')
        if date_str not in daily_data:
            daily_data[date_str] = {cat: 0 for cat in categories}
        display_cat = CategoryMapping.auto_categorize(cat2, work_name)
        daily_data[date_str][display_cat] = daily_data[date_str].get(display_cat, 0) + hours

    dates = sorted(daily_data.keys())
    result = {
        'labels': dates,
        'datasets': []
    }

    for cat in categories:
        data = [round(daily_data[d].get(cat, 0), 1) for d in dates]
        result['datasets'].append({
            'label': cat,
            'data': data,
            'backgroundColor': colors.get(cat, '#999999')
        })

    return jsonify(result)


@bp.route('/ranking')
def get_ranking():
    """業務別時間消費ランキングを取得"""
    category1 = request.args.get('category1')
    staff = request.args.get('staff')
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    default_rate = AppSetting.get_value('default_hourly_rate', 2000)
    hourly_rate = int(request.args.get('hourly_rate', default_rate))
    default_limit = AppSetting.get_value('ranking_limit', 10)
    limit = int(request.args.get('limit', default_limit))

    # 業務別に集計（1つのクエリで完結）
    work_stats = db.session.query(
        WorkRecord.work_name,
        WorkRecord.category2,
        func.sum(WorkRecord.quantity).label('total_hours'),
        func.sum(WorkRecord.total_amount).label('total_cost')
    )

    if category1:
        work_stats = work_stats.filter(WorkRecord.category1 == category1)
    if staff:
        work_stats = work_stats.filter(WorkRecord.staff_name == staff)
    if start_date:
        work_stats = work_stats.filter(WorkRecord.work_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        work_stats = work_stats.filter(WorkRecord.work_date <= datetime.strptime(end_date, '%Y-%m-%d').date())

    work_stats = work_stats.group_by(
        WorkRecord.work_name, WorkRecord.category2
    ).order_by(
        func.sum(WorkRecord.quantity).desc()
    ).limit(limit).all()

    # 全体の時間を計算（SQL集計）
    total_query = db.session.query(func.sum(WorkRecord.quantity))
    if category1:
        total_query = total_query.filter(WorkRecord.category1 == category1)
    if staff:
        total_query = total_query.filter(WorkRecord.staff_name == staff)
    if start_date:
        total_query = total_query.filter(WorkRecord.work_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        total_query = total_query.filter(WorkRecord.work_date <= datetime.strptime(end_date, '%Y-%m-%d').date())

    total_hours = total_query.scalar() or 0

    result = []
    for ws in work_stats:
        display_cat = CategoryMapping.auto_categorize(ws.category2, ws.work_name)
        is_reduction = CategoryMapping.is_target_for_reduction(display_cat)
        ratio = (ws.total_hours / total_hours * 100) if total_hours > 0 else 0

        result.append({
            'work_name': ws.work_name or '(未設定)',
            'category': display_cat,
            'original_category': ws.category2,
            'hours': round(ws.total_hours, 1),
            'ratio': round(ratio, 1),
            'cost': ws.total_cost,
            'estimated_cost': ws.total_hours * hourly_rate,
            'is_reduction_target': is_reduction
        })

    return jsonify(result)


@bp.route('/date-range')
def get_date_range():
    """データの日付範囲を取得"""
    min_date = db.session.query(func.min(WorkRecord.work_date)).scalar()
    max_date = db.session.query(func.max(WorkRecord.work_date)).scalar()

    return jsonify({
        'min_date': min_date.strftime('%Y-%m-%d') if min_date else None,
        'max_date': max_date.strftime('%Y-%m-%d') if max_date else None
    })


@bp.route('/categories/colors')
def get_category_colors():
    """カテゴリ色情報を取得（フロントエンド用）"""
    db_categories = DisplayCategory.query.order_by(DisplayCategory.sort_order).all()

    return jsonify({
        'categories': [c.name for c in db_categories],
        'colors': {c.name: c.color for c in db_categories},
        'reduction_targets': [c.name for c in db_categories if c.is_reduction_target],
        'badge_styles': {
            c.name: {
                'bg': c.badge_bg_color,
                'text': c.badge_text_color
            } for c in db_categories
        }
    })


@bp.route('/settings/defaults')
def get_default_settings():
    """デフォルト設定を取得"""
    return jsonify({
        'default_hourly_rate': AppSetting.get_value('default_hourly_rate', 2000),
        'ranking_limit': AppSetting.get_value('ranking_limit', 10),
        'default_category': AppSetting.get_value('default_category', 'コア業務')
    })
