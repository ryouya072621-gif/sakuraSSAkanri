from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import func, distinct
from app import db
from app.models import WorkRecord, CategoryMapping, DisplayCategory, AppSetting, TaskReductionTarget, ReductionGoal
from app.services.task_grouper import group_ranking_by_task_group, get_unit_type, get_unit_suffix, get_sub_category

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
        # カテゴリベースまたは業務名ベースで削減対象か判定
        is_category_reduction = CategoryMapping.is_target_for_reduction(display_cat)
        is_task_reduction = TaskReductionTarget.is_work_reduction_target(work_name)
        if is_category_reduction or is_task_reduction:
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
    """業務別時間消費ランキングを取得

    クエリパラメータ:
        group: 'true'の場合、中分類でグループ化して返す
    """
    category1 = request.args.get('category1')
    staff = request.args.get('staff')
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    group_by_task = request.args.get('group', '').lower() == 'true'
    default_rate = AppSetting.get_value('default_hourly_rate', 2000)
    hourly_rate = int(request.args.get('hourly_rate', default_rate))
    default_limit = AppSetting.get_value('ranking_limit', 10)
    # グループ化時はより多くのデータを取得（後でグループ化して絞る）
    limit = int(request.args.get('limit', default_limit))
    query_limit = limit * 10 if group_by_task else limit

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
    ).limit(query_limit).all()

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
        # カテゴリベースまたは業務名ベースで削減対象か判定
        is_category_reduction = CategoryMapping.is_target_for_reduction(display_cat)
        is_task_reduction = TaskReductionTarget.is_work_reduction_target(ws.work_name)
        is_reduction = is_category_reduction or is_task_reduction
        ratio = (ws.total_hours / total_hours * 100) if total_hours > 0 else 0

        # 単位タイプとサブカテゴリを取得
        unit_type = get_unit_type(ws.work_name)
        unit_suffix = get_unit_suffix(ws.work_name)
        sub_category = get_sub_category(ws.work_name)

        result.append({
            'work_name': ws.work_name or '(未設定)',
            'category': display_cat,
            'original_category': ws.category2,
            'hours': round(ws.total_hours, 1),
            'ratio': round(ratio, 1),
            'cost': ws.total_cost,
            'estimated_cost': ws.total_hours * hourly_rate,
            'is_reduction_target': is_reduction,
            'is_task_reduction_target': is_task_reduction,  # 業務名固有の削減対象フラグ
            'unit_type': unit_type,  # 'hours' or 'count'
            'unit_suffix': unit_suffix,  # 'h' or '件'
            'sub_category': sub_category  # サブカテゴリ（コア業務の細分化）
        })

    # グループ化が要求された場合
    if group_by_task:
        grouped = group_ranking_by_task_group(result)
        # limitを適用
        return jsonify(grouped[:limit])

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


@bp.route('/task/toggle-reduction-target', methods=['POST'])
def toggle_task_reduction_target():
    """業務名の削減対象フラグをトグル"""
    data = request.get_json()
    work_name = data.get('work_name')

    if not work_name:
        return jsonify({'error': '業務名が必要です'}), 400

    is_target = TaskReductionTarget.toggle_target(work_name)

    return jsonify({
        'work_name': work_name,
        'is_reduction_target': is_target
    })


@bp.route('/task/bulk-toggle-reduction-target', methods=['POST'])
def bulk_toggle_task_reduction_target():
    """複数の業務名を一括で削減対象に設定/解除"""
    data = request.get_json()
    work_names = data.get('work_names', [])
    set_as_target = data.get('set_as_target', True)  # True=削減対象に設定, False=解除

    if not work_names:
        return jsonify({'error': '業務名リストが必要です'}), 400

    TaskReductionTarget.bulk_set_targets(work_names, is_target=set_as_target)

    return jsonify({
        'updated_count': len(work_names),
        'work_names': work_names,
        'is_reduction_target': set_as_target
    })


@bp.route('/task/reduction-targets')
def get_task_reduction_targets():
    """削減対象として登録されている業務名一覧を取得"""
    targets = TaskReductionTarget.query.filter_by(is_reduction_target=True).all()
    return jsonify([{
        'work_name': t.work_name,
        'created_at': t.created_at.strftime('%Y-%m-%d %H:%M:%S')
    } for t in targets])


@bp.route('/reduction-goals')
def get_reduction_goals():
    """削減目標一覧を取得"""
    goals = ReductionGoal.query.filter_by(is_active=True).all()
    return jsonify([g.to_dict() for g in goals])


@bp.route('/reduction-goals', methods=['POST'])
def save_reduction_goal():
    """削減目標を保存"""
    data = request.get_json()

    goal_type = data.get('goal_type', 'global')
    target_percent = data.get('target_percent', 20.0)
    baseline_period_start = data.get('baseline_period_start')
    baseline_period_end = data.get('baseline_period_end')
    category_id = data.get('category_id')
    staff_name = data.get('staff_name')

    # 既存の同タイプの目標を探す
    query = ReductionGoal.query.filter_by(goal_type=goal_type, is_active=True)
    if goal_type == 'category' and category_id:
        query = query.filter_by(category_id=category_id)
    elif goal_type == 'staff' and staff_name:
        query = query.filter_by(staff_name=staff_name)

    goal = query.first()

    if goal:
        goal.target_percent = target_percent
        if baseline_period_start:
            goal.baseline_period_start = datetime.strptime(baseline_period_start, '%Y-%m-%d').date()
        if baseline_period_end:
            goal.baseline_period_end = datetime.strptime(baseline_period_end, '%Y-%m-%d').date()
    else:
        goal = ReductionGoal(
            goal_type=goal_type,
            target_percent=target_percent,
            category_id=category_id,
            staff_name=staff_name,
            is_active=True
        )
        if baseline_period_start:
            goal.baseline_period_start = datetime.strptime(baseline_period_start, '%Y-%m-%d').date()
        if baseline_period_end:
            goal.baseline_period_end = datetime.strptime(baseline_period_end, '%Y-%m-%d').date()
        db.session.add(goal)

    db.session.commit()

    return jsonify(goal.to_dict())


@bp.route('/reduction-goals/<int:goal_id>', methods=['DELETE'])
def delete_reduction_goal(goal_id):
    """削減目標を削除"""
    goal = ReductionGoal.query.get_or_404(goal_id)
    goal.is_active = False
    db.session.commit()
    return jsonify({'success': True})


# ============================================
# Phase 2: 分析API（推移グラフ・異常値検知）
# ============================================

@bp.route('/analytics/weekly-trend')
def get_weekly_trend():
    """週次推移データを取得"""
    category1 = request.args.get('category1')
    staff = request.args.get('staff')
    start_date = request.args.get('start')
    end_date = request.args.get('end')

    # 基本クエリ：日付・category2・work_nameごとに集計
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

    # 週ごとに集計（月曜開始）
    weekly_data = {}
    for work_date, cat2, work_name, hours in daily_stats:
        # 週の開始日（月曜日）を計算
        week_start = work_date - timedelta(days=work_date.weekday())
        week_key = week_start.strftime('%Y-%m-%d')

        if week_key not in weekly_data:
            weekly_data[week_key] = {'reduction': 0, 'core': 0, 'other': 0, 'total': 0}

        # カテゴリを判定
        display_cat = CategoryMapping.auto_categorize(cat2, work_name)
        is_category_reduction = CategoryMapping.is_target_for_reduction(display_cat)
        is_task_reduction = TaskReductionTarget.is_work_reduction_target(work_name)

        if is_category_reduction or is_task_reduction:
            weekly_data[week_key]['reduction'] += hours
        elif display_cat == 'コア業務':
            weekly_data[week_key]['core'] += hours
        else:
            weekly_data[week_key]['other'] += hours

        weekly_data[week_key]['total'] += hours

    # ソートして結果を構築
    sorted_weeks = sorted(weekly_data.keys())
    labels = []
    reduction_data = []
    core_data = []

    for week_key in sorted_weeks:
        week_date = datetime.strptime(week_key, '%Y-%m-%d')
        labels.append(f"W{week_date.isocalendar()[1]} ({week_date.strftime('%m/%d')})")
        reduction_data.append(round(weekly_data[week_key]['reduction'], 1))
        core_data.append(round(weekly_data[week_key]['core'], 1))

    # 目標データを取得
    goal = ReductionGoal.query.filter_by(goal_type='global', is_active=True).first()
    goal_data = None
    if goal and reduction_data:
        baseline = reduction_data[0] if reduction_data else 0
        target = baseline * (1 - goal.target_percent / 100)
        goal_data = {
            'baseline_hours': baseline,
            'target_hours': round(target, 1),
            'target_percent': goal.target_percent
        }

    return jsonify({
        'labels': labels,
        'datasets': [
            {
                'label': '削減対象',
                'data': reduction_data,
                'borderColor': '#dc2626',
                'backgroundColor': 'rgba(220, 38, 38, 0.1)',
                'tension': 0.3,
                'fill': True
            },
            {
                'label': 'コア業務',
                'data': core_data,
                'borderColor': '#3b82f6',
                'backgroundColor': 'rgba(59, 130, 246, 0.1)',
                'tension': 0.3,
                'fill': True
            }
        ],
        'goal': goal_data
    })


@bp.route('/analytics/alerts')
def get_alerts():
    """異常値アラートを取得"""
    category1 = request.args.get('category1')
    staff = request.args.get('staff')
    start_date = request.args.get('start')
    end_date = request.args.get('end')

    alerts = []

    # 直近2週間のデータを取得して比較
    today = datetime.now().date()
    if end_date:
        today = datetime.strptime(end_date, '%Y-%m-%d').date()

    this_week_start = today - timedelta(days=today.weekday())
    last_week_start = this_week_start - timedelta(days=7)
    last_week_end = this_week_start - timedelta(days=1)

    # 今週のカテゴリ別時間を集計
    def get_weekly_category_hours(week_start, week_end):
        query = db.session.query(
            WorkRecord.category2,
            WorkRecord.work_name,
            func.sum(WorkRecord.quantity).label('hours')
        ).filter(
            WorkRecord.work_date >= week_start,
            WorkRecord.work_date <= week_end
        )
        if category1:
            query = query.filter(WorkRecord.category1 == category1)
        if staff:
            query = query.filter(WorkRecord.staff_name == staff)

        stats = query.group_by(WorkRecord.category2, WorkRecord.work_name).all()

        category_hours = {}
        total_hours = 0
        for cat2, work_name, hours in stats:
            display_cat = CategoryMapping.auto_categorize(cat2, work_name)
            category_hours[display_cat] = category_hours.get(display_cat, 0) + hours
            total_hours += hours

        return category_hours, total_hours

    this_week_hours, this_week_total = get_weekly_category_hours(this_week_start, today)
    last_week_hours, last_week_total = get_weekly_category_hours(last_week_start, last_week_end)

    # 1. 週次比較アラート（+50%以上の変動）
    # 最低時間閾値を使用してノイズを除去
    min_hours = current_app.config.get('ALERT_MIN_HOURS', 5)
    change_threshold = current_app.config.get('ALERT_CHANGE_THRESHOLD', 50)

    for category, current_hours in this_week_hours.items():
        prev_hours = last_week_hours.get(category, 0)
        if prev_hours >= min_hours:  # 最低時間以上の場合のみアラート判定
            change_percent = ((current_hours - prev_hours) / prev_hours) * 100
            if change_percent >= change_threshold:
                alerts.append({
                    'level': 'critical',
                    'type': 'week_over_week',
                    'message': f'今週の「{category}」時間が先週比 +{round(change_percent)}%',
                    'category': category,
                    'current_value': round(current_hours, 1),
                    'previous_value': round(prev_hours, 1),
                    'change_percent': round(change_percent, 1)
                })

    # 2. 削減対象カテゴリの閾値チェック
    reduction_categories = DisplayCategory.query.filter_by(is_reduction_target=True).all()
    reduction_names = {c.name for c in reduction_categories}

    reduction_total = sum(hours for cat, hours in this_week_hours.items() if cat in reduction_names)
    task_reduction_total = 0

    # タスクベースの削減対象も計算
    for cat2, work_name, hours in db.session.query(
        WorkRecord.category2, WorkRecord.work_name, func.sum(WorkRecord.quantity)
    ).filter(
        WorkRecord.work_date >= this_week_start,
        WorkRecord.work_date <= today
    ).group_by(WorkRecord.category2, WorkRecord.work_name).all():
        if TaskReductionTarget.is_work_reduction_target(work_name):
            display_cat = CategoryMapping.auto_categorize(cat2, work_name)
            if display_cat not in reduction_names:
                task_reduction_total += hours

    total_reduction = reduction_total + task_reduction_total

    if this_week_total > 0:
        reduction_ratio = (total_reduction / this_week_total) * 100
        reduction_warning_threshold = current_app.config.get('REDUCTION_RATIO_WARNING', 15)
        if reduction_ratio > reduction_warning_threshold:
            alerts.append({
                'level': 'warning',
                'type': 'threshold_exceeded',
                'message': f'削減対象業務が全体の{round(reduction_ratio, 1)}%を超えています',
                'category': '削減対象全体',
                'current_ratio': round(reduction_ratio, 1),
                'threshold': reduction_warning_threshold
            })

    # 3. 削減目標進捗チェック
    goal = ReductionGoal.query.filter_by(goal_type='global', is_active=True).first()
    if goal:
        # 基準期間のデータを取得
        baseline_query = db.session.query(
            func.sum(WorkRecord.quantity)
        )
        if goal.baseline_period_start and goal.baseline_period_end:
            baseline_query = baseline_query.filter(
                WorkRecord.work_date >= goal.baseline_period_start,
                WorkRecord.work_date <= goal.baseline_period_end
            )
        if category1:
            baseline_query = baseline_query.filter(WorkRecord.category1 == category1)
        if staff:
            baseline_query = baseline_query.filter(WorkRecord.staff_name == staff)

        baseline_total = baseline_query.scalar() or 0

        if baseline_total > 0:
            target_reduction = goal.target_percent
            current_reduction = ((baseline_total - this_week_total) / baseline_total) * 100 if baseline_total > 0 else 0
            progress = (current_reduction / target_reduction) * 100 if target_reduction > 0 else 0

            if progress >= 80:
                alerts.append({
                    'level': 'success',
                    'type': 'goal_progress',
                    'message': '削減対象業務は目標通り推移しています',
                    'progress_percent': round(progress, 1)
                })
            elif progress < 50:
                alerts.append({
                    'level': 'warning',
                    'type': 'goal_progress',
                    'message': f'削減目標の達成率が{round(progress, 1)}%です',
                    'progress_percent': round(progress, 1)
                })

    return jsonify({'alerts': alerts})


@bp.route('/analytics/reduction-progress')
def get_reduction_progress():
    """削減目標進捗を取得"""
    category1 = request.args.get('category1')
    staff = request.args.get('staff')
    start_date = request.args.get('start')
    end_date = request.args.get('end')

    # 現在の削減対象時間を計算
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

    stats = query.group_by(WorkRecord.category2, WorkRecord.work_name).all()

    current_reduction = 0
    total_hours = 0
    for cat2, work_name, hours in stats:
        display_cat = CategoryMapping.auto_categorize(cat2, work_name)
        is_category_reduction = CategoryMapping.is_target_for_reduction(display_cat)
        is_task_reduction = TaskReductionTarget.is_work_reduction_target(work_name)
        if is_category_reduction or is_task_reduction:
            current_reduction += hours
        total_hours += hours

    # 目標を取得
    goal = ReductionGoal.query.filter_by(goal_type='global', is_active=True).first()

    result = {
        'current_hours': round(current_reduction, 1),
        'total_hours': round(total_hours, 1),
        'current_ratio': round((current_reduction / total_hours * 100) if total_hours > 0 else 0, 1)
    }

    if goal:
        baseline = goal.baseline_hours or current_reduction
        target = baseline * (1 - goal.target_percent / 100)
        reduction_achieved = ((baseline - current_reduction) / baseline * 100) if baseline > 0 else 0
        progress = (reduction_achieved / goal.target_percent * 100) if goal.target_percent > 0 else 0

        result.update({
            'baseline_hours': round(baseline, 1),
            'target_hours': round(target, 1),
            'target_reduction': goal.target_percent,
            'reduction_achieved': round(reduction_achieved, 1),
            'progress_percent': round(min(progress, 100), 1),
            'status': 'on_track' if progress >= 80 else 'behind' if progress < 50 else 'moderate'
        })

    return jsonify(result)


# ============================================
# Phase 3: スタッフ別比較API
# ============================================

@bp.route('/analytics/staff-comparison')
def get_staff_comparison():
    """スタッフ別比較データを取得"""
    category1 = request.args.get('category1')
    start_date = request.args.get('start')
    end_date = request.args.get('end')

    # スタッフ別の業務時間を集計
    query = db.session.query(
        WorkRecord.staff_name,
        WorkRecord.category2,
        WorkRecord.work_name,
        func.sum(WorkRecord.quantity).label('hours')
    )

    if category1:
        query = query.filter(WorkRecord.category1 == category1)
    if start_date:
        query = query.filter(WorkRecord.work_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(WorkRecord.work_date <= datetime.strptime(end_date, '%Y-%m-%d').date())

    stats = query.group_by(WorkRecord.staff_name, WorkRecord.category2, WorkRecord.work_name).all()

    # スタッフごとに集計
    staff_data = {}
    for staff_name, cat2, work_name, hours in stats:
        if not staff_name:
            continue

        if staff_name not in staff_data:
            staff_data[staff_name] = {
                'total_hours': 0,
                'core_hours': 0,
                'reduction_hours': 0,
                'other_hours': 0,
                'categories': {}
            }

        display_cat = CategoryMapping.auto_categorize(cat2, work_name)
        is_category_reduction = CategoryMapping.is_target_for_reduction(display_cat)
        is_task_reduction = TaskReductionTarget.is_work_reduction_target(work_name)

        staff_data[staff_name]['total_hours'] += hours
        staff_data[staff_name]['categories'][display_cat] = staff_data[staff_name]['categories'].get(display_cat, 0) + hours

        if is_category_reduction or is_task_reduction:
            staff_data[staff_name]['reduction_hours'] += hours
        elif display_cat == 'コア業務':
            staff_data[staff_name]['core_hours'] += hours
        else:
            staff_data[staff_name]['other_hours'] += hours

    # 結果を構築
    result = []
    for staff_name, data in staff_data.items():
        total = data['total_hours']
        if total == 0:
            continue

        core_ratio = (data['core_hours'] / total * 100) if total > 0 else 0
        reduction_ratio = (data['reduction_hours'] / total * 100) if total > 0 else 0

        # 効率スコア（コア業務率が高く、削減対象率が低いほど高スコア）
        efficiency_score = core_ratio - (reduction_ratio * 0.5)

        result.append({
            'staff_name': staff_name,
            'total_hours': round(total, 1),
            'core_hours': round(data['core_hours'], 1),
            'core_ratio': round(core_ratio, 1),
            'reduction_hours': round(data['reduction_hours'], 1),
            'reduction_ratio': round(reduction_ratio, 1),
            'other_hours': round(data['other_hours'], 1),
            'efficiency_score': round(efficiency_score, 1),
            'categories': {cat: round(hours, 1) for cat, hours in data['categories'].items()}
        })

    # 効率スコアでソート（降順）
    result.sort(key=lambda x: x['efficiency_score'], reverse=True)

    # 星評価を追加（ハイブリッド方式：絶対評価 + 相対評価）
    # 絶対評価閾値を取得
    excellent_threshold = current_app.config.get('STAR_EXCELLENT_THRESHOLD', 80)
    good_threshold = current_app.config.get('STAR_GOOD_THRESHOLD', 50)

    n = len(result)
    for i, item in enumerate(result):
        score = item['efficiency_score']

        # まず絶対評価で判定
        if score >= excellent_threshold:
            # 効率スコア80以上は無条件で★★★
            item['stars'] = 3
        elif score >= good_threshold:
            # 効率スコア50以上は最低★★を保証、相対評価で★★★になる可能性あり
            if n <= 3:
                relative_stars = 3 - i
            else:
                if i < n / 3:
                    relative_stars = 3
                elif i < 2 * n / 3:
                    relative_stars = 2
                else:
                    relative_stars = 1
            item['stars'] = max(2, relative_stars)  # 最低★★を保証
        else:
            # 50未満は相対評価のみ
            if n <= 3:
                item['stars'] = max(1, 3 - i)
            else:
                if i < n / 3:
                    item['stars'] = 3
                elif i < 2 * n / 3:
                    item['stars'] = 2
                else:
                    item['stars'] = 1

    # カテゴリ別比較用データ
    all_categories = set()
    for item in result:
        all_categories.update(item['categories'].keys())

    # カテゴリ色を取得
    db_categories = DisplayCategory.query.order_by(DisplayCategory.sort_order).all()
    category_colors = {c.name: c.color for c in db_categories}

    return jsonify({
        'staff': result,
        'categories': list(all_categories),
        'category_colors': category_colors
    })
