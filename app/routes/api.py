from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import func, distinct
from app import db
from app.models import WorkRecord, CategoryMapping, DisplayCategory, AppSetting, TaskReductionTarget, ReductionGoal, WorkProjectMapping, STANDARD_TASK_TYPES
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
    """集計サマリーを取得（時間制と件数制を分離）"""
    category1 = request.args.get('category1')
    staff = request.args.get('staff')
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    default_rate = AppSetting.get_value('default_hourly_rate', 2000)
    hourly_rate = int(request.args.get('hourly_rate', default_rate))

    # work_name別に集計（unit_type判定のため）
    query = db.session.query(
        WorkRecord.category2,
        WorkRecord.work_name,
        func.sum(WorkRecord.quantity).label('quantity'),
        func.sum(WorkRecord.total_amount).label('cost'),
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

    # タスク種類数
    task_types = len(set(r.work_name for r in stats if r.work_name))

    # 時間制と件数制を分離 + 削減対象を同時計算
    total_hours = 0
    total_count = 0
    total_cost = 0
    reduction_hours = 0

    for cat2, work_name, quantity, cost in stats:
        qty = quantity or 0
        unit_type = get_unit_type(work_name)

        if unit_type == 'count':
            total_count += qty
        else:
            total_hours += qty

        total_cost += cost or 0

        # 削減対象判定（時間制のみ）
        if unit_type != 'count':
            display_cat = CategoryMapping.auto_categorize(cat2, work_name)
            is_category_reduction = CategoryMapping.is_target_for_reduction(display_cat)
            is_task_reduction = TaskReductionTarget.is_work_reduction_target(work_name)
            if is_category_reduction or is_task_reduction:
                reduction_hours += qty

    reduction_ratio = (reduction_hours / total_hours * 100) if total_hours > 0 else 0

    return jsonify({
        'total_hours': round(total_hours, 1),
        'total_count': round(total_count, 1),
        'total_cost': total_cost,
        'estimated_cost': round(total_hours * hourly_rate),
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


# ============================================
# Phase 4: プロジェクト×作業タイプ分析API
# ============================================

@bp.route('/project-breakdown')
def get_project_breakdown():
    """
    プロジェクト×作業タイプのマトリクス分析データを取得

    Response:
    {
        "matrix": {
            "ベネッセ": {"MTG・会議": 10.5, "資料作成": 5.0, ...},
            "社内（経理部）": {"データ入力": 20.0, ...},
            ...
        },
        "projects": ["ベネッセ", "社内（経理部）", ...],
        "task_types": ["MTG・会議", "資料作成", ...],
        "project_totals": {"ベネッセ": 15.5, ...},
        "task_type_totals": {"MTG・会議": 30.0, ...},
        "grand_total": 100.0
    }
    """
    category1 = request.args.get('category1')
    staff = request.args.get('staff')
    start_date = request.args.get('start')
    end_date = request.args.get('end')

    # WorkRecordとWorkProjectMappingを結合してデータを取得
    query = db.session.query(
        WorkRecord.work_name,
        WorkProjectMapping.project,
        WorkProjectMapping.task_type,
        func.sum(WorkRecord.quantity).label('hours')
    ).outerjoin(
        WorkProjectMapping,
        WorkRecord.work_name == WorkProjectMapping.work_name
    )

    if category1:
        query = query.filter(WorkRecord.category1 == category1)
    if staff:
        query = query.filter(WorkRecord.staff_name == staff)
    if start_date:
        query = query.filter(WorkRecord.work_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(WorkRecord.work_date <= datetime.strptime(end_date, '%Y-%m-%d').date())

    results = query.group_by(
        WorkRecord.work_name,
        WorkProjectMapping.project,
        WorkProjectMapping.task_type
    ).all()

    # マトリクスを構築
    matrix = {}
    project_totals = {}
    task_type_totals = {}
    grand_total = 0

    for work_name, project, task_type, hours in results:
        # マッピングがない場合はデフォルト値
        proj = project or '未分類'
        tt = task_type or 'その他'

        if proj not in matrix:
            matrix[proj] = {}

        matrix[proj][tt] = matrix[proj].get(tt, 0) + (hours or 0)
        project_totals[proj] = project_totals.get(proj, 0) + (hours or 0)
        task_type_totals[tt] = task_type_totals.get(tt, 0) + (hours or 0)
        grand_total += hours or 0

    # プロジェクトを時間順にソート
    sorted_projects = sorted(project_totals.keys(), key=lambda x: project_totals[x], reverse=True)

    # 作業タイプを時間順にソート
    sorted_task_types = sorted(task_type_totals.keys(), key=lambda x: task_type_totals[x], reverse=True)

    # 値を丸める
    for proj in matrix:
        for tt in matrix[proj]:
            matrix[proj][tt] = round(matrix[proj][tt], 1)

    return jsonify({
        'matrix': matrix,
        'projects': sorted_projects,
        'task_types': sorted_task_types,
        'project_totals': {k: round(v, 1) for k, v in project_totals.items()},
        'task_type_totals': {k: round(v, 1) for k, v in task_type_totals.items()},
        'grand_total': round(grand_total, 1)
    })


@bp.route('/project-summary')
def get_project_summary():
    """
    プロジェクト別サマリーを取得（上位N件）

    Response:
    {
        "projects": [
            {
                "name": "ベネッセ",
                "total_hours": 50.5,
                "percentage": 25.3,
                "top_task_type": "MTG・会議",
                "task_breakdown": {"MTG・会議": 20.0, "資料作成": 15.5, ...}
            },
            ...
        ]
    }
    """
    category1 = request.args.get('category1')
    staff = request.args.get('staff')
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    limit = int(request.args.get('limit', 10))

    # WorkRecordとWorkProjectMappingを結合
    query = db.session.query(
        WorkProjectMapping.project,
        WorkProjectMapping.task_type,
        func.sum(WorkRecord.quantity).label('hours')
    ).outerjoin(
        WorkProjectMapping,
        WorkRecord.work_name == WorkProjectMapping.work_name
    )

    if category1:
        query = query.filter(WorkRecord.category1 == category1)
    if staff:
        query = query.filter(WorkRecord.staff_name == staff)
    if start_date:
        query = query.filter(WorkRecord.work_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(WorkRecord.work_date <= datetime.strptime(end_date, '%Y-%m-%d').date())

    results = query.group_by(
        WorkProjectMapping.project,
        WorkProjectMapping.task_type
    ).all()

    # プロジェクトごとに集計
    project_data = {}
    grand_total = 0

    for project, task_type, hours in results:
        proj = project or '未分類'
        tt = task_type or 'その他'

        if proj not in project_data:
            project_data[proj] = {'total': 0, 'tasks': {}}

        project_data[proj]['total'] += hours or 0
        project_data[proj]['tasks'][tt] = project_data[proj]['tasks'].get(tt, 0) + (hours or 0)
        grand_total += hours or 0

    # 結果を構築
    projects = []
    for proj, data in sorted(project_data.items(), key=lambda x: x[1]['total'], reverse=True)[:limit]:
        top_task = max(data['tasks'].items(), key=lambda x: x[1])[0] if data['tasks'] else 'なし'
        projects.append({
            'name': proj,
            'total_hours': round(data['total'], 1),
            'percentage': round(data['total'] / grand_total * 100, 1) if grand_total > 0 else 0,
            'top_task_type': top_task,
            'task_breakdown': {k: round(v, 1) for k, v in data['tasks'].items()}
        })

    return jsonify({
        'projects': projects,
        'grand_total': round(grand_total, 1)
    })


@bp.route('/unmapped-work-items')
def get_unmapped_work_items():
    """
    まだプロジェクトマッピングされていない業務名を取得

    Response:
    {
        "items": [
            {"work_name": "...", "category1": "...", "category2": "...", "total_hours": 10.5},
            ...
        ],
        "total": 50
    }
    """
    category1 = request.args.get('category1')
    limit = int(request.args.get('limit', 100))

    # マッピングされていない業務名を取得
    subquery = db.session.query(WorkProjectMapping.work_name)

    query = db.session.query(
        WorkRecord.work_name,
        WorkRecord.category1,
        WorkRecord.category2,
        func.sum(WorkRecord.quantity).label('total_hours')
    ).filter(
        ~WorkRecord.work_name.in_(subquery)
    )

    if category1:
        query = query.filter(WorkRecord.category1 == category1)

    results = query.group_by(
        WorkRecord.work_name,
        WorkRecord.category1,
        WorkRecord.category2
    ).order_by(func.sum(WorkRecord.quantity).desc()).limit(limit).all()

    items = [
        {
            'work_name': r.work_name,
            'category1': r.category1,
            'category2': r.category2,
            'total_hours': round(r.total_hours, 1)
        }
        for r in results
    ]

    return jsonify({
        'items': items,
        'total': len(items)
    })


# ============================================
# 部門比較・価値ランク分析 API
# ============================================

@bp.route('/analytics/value-breakdown')
def get_value_breakdown():
    """価値ランク別の業務時間集計"""
    category1 = request.args.get('category1')
    staff = request.args.get('staff')
    start_date = request.args.get('start')
    end_date = request.args.get('end')

    # category2+work_nameごとの時間を取得
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

    results = query.group_by(WorkRecord.category2, WorkRecord.work_name).all()

    # カテゴリ→価値ランクのマッピングを取得
    categories = DisplayCategory.query.all()
    cat_rank_map = {c.name: (c.value_rank or 'A') for c in categories}
    cat_color_map = {c.name: c.color for c in categories}

    # 価値ランク別に集計
    rank_data = {'S': 0, 'A': 0, 'B': 0, 'C': 0}
    rank_details = {'S': [], 'A': [], 'B': [], 'C': []}

    CategoryMapping.clear_cache()
    for cat2, work_name, hours in results:
        display_cat = CategoryMapping.auto_categorize(cat2, work_name)
        rank = cat_rank_map.get(display_cat, 'A')
        h = hours or 0
        rank_data[rank] += h
        rank_details[rank].append({
            'category': display_cat,
            'work_name': work_name,
            'hours': round(h, 1)
        })

    # 各ランクのdetailsを時間降順でソート、上位10件に絞る
    for rank in rank_details:
        rank_details[rank].sort(key=lambda x: x['hours'], reverse=True)
        rank_details[rank] = rank_details[rank][:10]

    total = sum(rank_data.values())
    rank_labels = {
        'S': '高価値', 'A': '中価値', 'B': '低価値', 'C': '無駄'
    }
    rank_colors = {
        'S': '#16a34a', 'A': '#2563eb', 'B': '#ca8a04', 'C': '#dc2626'
    }

    return jsonify({
        'ranks': [
            {
                'rank': r,
                'label': rank_labels[r],
                'hours': round(rank_data[r], 1),
                'percentage': round(rank_data[r] / total * 100, 1) if total > 0 else 0,
                'color': rank_colors[r],
                'top_items': rank_details[r]
            }
            for r in ['S', 'A', 'B', 'C']
        ],
        'total_hours': round(total, 1)
    })


@bp.route('/analytics/department-comparison')
def get_department_comparison():
    """全部門比較データ"""
    start_date = request.args.get('start')
    end_date = request.args.get('end')

    # 部門一覧を取得
    dept_query = db.session.query(WorkRecord.category1).distinct()
    departments = [d.category1 for d in dept_query.all() if d.category1]

    # カテゴリ→価値ランクのマッピング
    categories = DisplayCategory.query.all()
    cat_rank_map = {c.name: (c.value_rank or 'A') for c in categories}

    CategoryMapping.clear_cache()

    dept_data = []
    for dept in departments:
        query = db.session.query(
            WorkRecord.category2,
            WorkRecord.work_name,
            func.sum(WorkRecord.quantity).label('hours')
        ).filter(WorkRecord.category1 == dept)

        if start_date:
            query = query.filter(WorkRecord.work_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
        if end_date:
            query = query.filter(WorkRecord.work_date <= datetime.strptime(end_date, '%Y-%m-%d').date())

        results = query.group_by(WorkRecord.category2, WorkRecord.work_name).all()

        rank_hours = {'S': 0, 'A': 0, 'B': 0, 'C': 0}
        for cat2, work_name, hours in results:
            display_cat = CategoryMapping.auto_categorize(cat2, work_name)
            rank = cat_rank_map.get(display_cat, 'A')
            rank_hours[rank] += hours or 0

        total = sum(rank_hours.values())
        s_ratio = round(rank_hours['S'] / total * 100, 1) if total > 0 else 0
        waste_ratio = round((rank_hours['B'] + rank_hours['C']) / total * 100, 1) if total > 0 else 0

        # スタッフ数
        staff_count = db.session.query(func.count(distinct(WorkRecord.staff_name))).filter(
            WorkRecord.category1 == dept
        ).scalar() or 0

        dept_data.append({
            'department': dept,
            'total_hours': round(total, 1),
            'staff_count': staff_count,
            'rank_hours': {k: round(v, 1) for k, v in rank_hours.items()},
            'high_value_ratio': s_ratio,
            'waste_ratio': waste_ratio,
            'efficiency_score': round(s_ratio - waste_ratio * 0.5, 1)
        })

    # 効率スコア降順でソート
    dept_data.sort(key=lambda x: x['efficiency_score'], reverse=True)

    return jsonify({
        'departments': dept_data,
        'rank_colors': {'S': '#16a34a', 'A': '#2563eb', 'B': '#ca8a04', 'C': '#dc2626'},
        'rank_labels': {'S': '高価値', 'A': '中価値', 'B': '低価値', 'C': '無駄'}
    })


@bp.route('/analytics/department-detail')
def get_department_detail():
    """個別部門の詳細データ"""
    department = request.args.get('department')
    start_date = request.args.get('start')
    end_date = request.args.get('end')

    if not department:
        return jsonify({'error': 'department parameter is required'}), 400

    # カテゴリ→価値ランク
    categories = DisplayCategory.query.all()
    cat_rank_map = {c.name: (c.value_rank or 'A') for c in categories}
    cat_color_map = {c.name: c.color for c in categories}

    CategoryMapping.clear_cache()

    # 業務名別の集計
    query = db.session.query(
        WorkRecord.category2,
        WorkRecord.work_name,
        func.sum(WorkRecord.quantity).label('hours')
    ).filter(WorkRecord.category1 == department)

    if start_date:
        query = query.filter(WorkRecord.work_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(WorkRecord.work_date <= datetime.strptime(end_date, '%Y-%m-%d').date())

    results = query.group_by(WorkRecord.category2, WorkRecord.work_name).all()

    # 価値ランク別集計 + 削減インパクトTOP10
    rank_hours = {'S': 0, 'A': 0, 'B': 0, 'C': 0}
    reduction_candidates = []

    for cat2, work_name, hours in results:
        display_cat = CategoryMapping.auto_categorize(cat2, work_name)
        rank = cat_rank_map.get(display_cat, 'A')
        h = hours or 0
        rank_hours[rank] += h

        if rank in ('B', 'C'):
            reduction_candidates.append({
                'work_name': work_name,
                'category': display_cat,
                'rank': rank,
                'hours': round(h, 1)
            })

    reduction_candidates.sort(key=lambda x: x['hours'], reverse=True)

    # スタッフ別構成
    staff_query = db.session.query(
        WorkRecord.staff_name,
        WorkRecord.category2,
        WorkRecord.work_name,
        func.sum(WorkRecord.quantity).label('hours')
    ).filter(WorkRecord.category1 == department)

    if start_date:
        staff_query = staff_query.filter(WorkRecord.work_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        staff_query = staff_query.filter(WorkRecord.work_date <= datetime.strptime(end_date, '%Y-%m-%d').date())

    staff_results = staff_query.group_by(
        WorkRecord.staff_name, WorkRecord.category2, WorkRecord.work_name
    ).all()

    staff_data = {}
    for staff_name, cat2, work_name, hours in staff_results:
        if staff_name not in staff_data:
            staff_data[staff_name] = {'S': 0, 'A': 0, 'B': 0, 'C': 0}
        display_cat = CategoryMapping.auto_categorize(cat2, work_name)
        rank = cat_rank_map.get(display_cat, 'A')
        staff_data[staff_name][rank] += hours or 0

    staff_comparison = [
        {
            'name': name,
            'rank_hours': {k: round(v, 1) for k, v in ranks.items()},
            'total': round(sum(ranks.values()), 1)
        }
        for name, ranks in sorted(staff_data.items(), key=lambda x: sum(x[1].values()), reverse=True)
    ]

    total = sum(rank_hours.values())

    return jsonify({
        'department': department,
        'total_hours': round(total, 1),
        'rank_hours': {k: round(v, 1) for k, v in rank_hours.items()},
        'reduction_candidates': reduction_candidates[:10],
        'staff_comparison': staff_comparison,
        'rank_colors': {'S': '#16a34a', 'A': '#2563eb', 'B': '#ca8a04', 'C': '#dc2626'}
    })


@bp.route('/analytics/capacity-simulation')
def get_capacity_simulation():
    """業務倍増シミュレーション用データ"""
    category1 = request.args.get('category1')
    start_date = request.args.get('start')
    end_date = request.args.get('end')

    # カテゴリ→価値ランク
    categories = DisplayCategory.query.all()
    cat_rank_map = {c.name: (c.value_rank or 'A') for c in categories}

    CategoryMapping.clear_cache()

    query = db.session.query(
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

    results = query.group_by(WorkRecord.category2, WorkRecord.work_name).all()

    # ランク別に業務をリスト化
    rank_items = {'S': [], 'A': [], 'B': [], 'C': []}
    for cat2, work_name, hours in results:
        display_cat = CategoryMapping.auto_categorize(cat2, work_name)
        rank = cat_rank_map.get(display_cat, 'A')
        rank_items[rank].append({
            'work_name': work_name,
            'category': display_cat,
            'hours': round(hours or 0, 1)
        })

    # 各ランクを時間降順ソート
    for rank in rank_items:
        rank_items[rank].sort(key=lambda x: x['hours'], reverse=True)

    rank_totals = {r: round(sum(i['hours'] for i in items), 1) for r, items in rank_items.items()}
    total = sum(rank_totals.values())

    return jsonify({
        'total_hours': round(total, 1),
        'rank_totals': rank_totals,
        'rank_items': {r: items[:20] for r, items in rank_items.items()},
        'rank_colors': {'S': '#16a34a', 'A': '#2563eb', 'B': '#ca8a04', 'C': '#dc2626'},
        'rank_labels': {'S': '高価値', 'A': '中価値', 'B': '低価値', 'C': '無駄'}
    })


# ============================================
# 月次目標進捗API
# ============================================

@bp.route('/analytics/monthly-goals')
def get_monthly_goals():
    """部門別の月次目標進捗データ"""
    from app.models import MonthlyGoal

    department = request.args.get('department')
    year_month = request.args.get('year_month')

    query = MonthlyGoal.query

    if department:
        query = query.filter_by(department_name=department)
    if year_month:
        query = query.filter_by(year_month=year_month)

    goals = query.order_by(
        MonthlyGoal.department_name,
        MonthlyGoal.year_month.desc(),
        MonthlyGoal.goal_index
    ).all()

    # 部門別に集約
    dept_goals = {}
    for g in goals:
        dept = g.department_name
        if dept not in dept_goals:
            dept_goals[dept] = {'months': {}, 'avg_progress': 0}

        ym = g.year_month
        if ym not in dept_goals[dept]['months']:
            dept_goals[dept]['months'][ym] = []
        dept_goals[dept]['months'][ym].append(g.to_dict())

    # 部門ごとの平均進捗率を計算（最新月）
    for dept, data in dept_goals.items():
        if data['months']:
            latest_ym = max(data['months'].keys())
            latest_goals = data['months'][latest_ym]
            valid_goals = [g for g in latest_goals if g['progress_pct'] and g['progress_pct'] > 0]
            if valid_goals:
                data['avg_progress'] = round(
                    sum(g['progress_pct'] for g in valid_goals) / len(valid_goals)
                )
            data['latest_month'] = latest_ym

    # 月別推移データ（全部門）
    all_months = sorted(set(g.year_month for g in goals))
    trend_data = {}
    for ym in all_months:
        ym_goals = [g for g in goals if g.year_month == ym and g.progress_pct and g.progress_pct > 0]
        if ym_goals:
            trend_data[ym] = round(sum(g.progress_pct for g in ym_goals) / len(ym_goals))

    return jsonify({
        'departments': dept_goals,
        'trend': trend_data,
        'months': all_months,
    })
