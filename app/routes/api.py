from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import func, distinct
from app import db
from app.models import WorkRecord, CategoryMapping, DisplayCategory, AppSetting, WorkProjectMapping, STANDARD_TASK_TYPES, WorkTypeClassification, WORK_TYPE_CHOICES
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

    # 時間制と件数制を分離
    total_hours = 0
    total_count = 0
    total_cost = 0

    for cat2, work_name, quantity, cost in stats:
        qty = quantity or 0
        unit_type = get_unit_type(work_name)

        if unit_type == 'count':
            total_count += qty
        else:
            total_hours += qty

        total_cost += cost or 0

    return jsonify({
        'total_hours': round(total_hours, 1),
        'total_count': round(total_count, 1),
        'total_cost': total_cost,
        'estimated_cost': round(total_hours * hourly_rate),
        'task_types': task_types
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
            'unit_type': unit_type,
            'unit_suffix': unit_suffix,
            'sub_category': sub_category
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
        week_start = work_date - timedelta(days=work_date.weekday())
        week_key = week_start.strftime('%Y-%m-%d')

        if week_key not in weekly_data:
            weekly_data[week_key] = 0
        weekly_data[week_key] += hours

    # ソートして結果を構築
    sorted_weeks = sorted(weekly_data.keys())
    labels = []
    total_data = []

    for week_key in sorted_weeks:
        week_date = datetime.strptime(week_key, '%Y-%m-%d')
        labels.append(f"W{week_date.isocalendar()[1]} ({week_date.strftime('%m/%d')})")
        total_data.append(round(weekly_data[week_key], 1))

    return jsonify({
        'labels': labels,
        'datasets': [
            {
                'label': '合計時間',
                'data': total_data,
                'borderColor': '#6366f1',
                'backgroundColor': 'rgba(99, 102, 241, 0.1)',
                'tension': 0.3,
                'fill': True
            }
        ]
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

    return jsonify({'alerts': alerts})


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
                'other_hours': 0,
                'categories': {}
            }

        display_cat = CategoryMapping.auto_categorize(cat2, work_name)

        staff_data[staff_name]['total_hours'] += hours
        staff_data[staff_name]['categories'][display_cat] = staff_data[staff_name]['categories'].get(display_cat, 0) + hours

        if display_cat == 'コア業務':
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

        # 効率スコア（コア業務率）
        efficiency_score = core_ratio

        result.append({
            'staff_name': staff_name,
            'total_hours': round(total, 1),
            'core_hours': round(data['core_hours'], 1),
            'core_ratio': round(core_ratio, 1),
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


# ============================================
# 部門月次比較（前月 vs 今月）
# ============================================

def _month_format_expr():
    """PostgreSQL/SQLite両対応の月フォーマット式"""
    is_pg = str(db.engine.url).startswith('postgresql')
    if is_pg:
        return func.to_char(WorkRecord.work_date, 'YYYY-MM')
    else:
        return func.strftime('%Y-%m', WorkRecord.work_date)


def _parse_month_range(month_str):
    """'YYYY-MM' → (first_day, last_day) を返す"""
    from calendar import monthrange
    parts = month_str.split('-')
    year, month = int(parts[0]), int(parts[1])
    last_day = monthrange(year, month)[1]
    from datetime import date
    return date(year, month, 1), date(year, month, last_day)


def _sum_hours_only(department, start, end):
    """時間制レコードのみ合計（件数制を除外）。(hours, count) を返す"""
    rows = db.session.query(
        WorkRecord.work_name,
        func.sum(WorkRecord.quantity).label('qty'),
    ).filter(
        WorkRecord.category1 == department,
        WorkRecord.work_date >= start,
        WorkRecord.work_date <= end,
    ).group_by(WorkRecord.work_name).all()

    total_hours = 0.0
    total_count = 0.0
    for work_name, qty in rows:
        q = float(qty or 0)
        if get_unit_type(work_name) == 'count':
            total_count += q
        else:
            total_hours += q
    return total_hours, total_count


def get_department_month_detail_data(department, base_month, compare_month):
    """部門月次比較の詳細データを取得（API/AI共用ヘルパー）"""
    base_start, base_end = _parse_month_range(base_month)
    comp_start, comp_end = _parse_month_range(compare_month)

    CategoryMapping.clear_cache()

    # --- サマリー（時間制のみ） ---
    base_hours, base_count = _sum_hours_only(department, base_start, base_end)
    comp_hours, comp_count = _sum_hours_only(department, comp_start, comp_end)

    # コストは全レコード合計（コストは混在しない）
    base_cost_val = db.session.query(
        func.coalesce(func.sum(WorkRecord.total_amount), 0),
    ).filter(
        WorkRecord.category1 == department,
        WorkRecord.work_date >= base_start,
        WorkRecord.work_date <= base_end,
    ).scalar() or 0
    comp_cost_val = db.session.query(
        func.coalesce(func.sum(WorkRecord.total_amount), 0),
    ).filter(
        WorkRecord.category1 == department,
        WorkRecord.work_date >= comp_start,
        WorkRecord.work_date <= comp_end,
    ).scalar() or 0

    base_cost = float(base_cost_val)
    comp_cost = float(comp_cost_val)
    diff_hours = comp_hours - base_hours
    diff_pct = round(diff_hours / base_hours * 100, 1) if base_hours > 0 else (0 if diff_hours == 0 else None)

    # 効率指標
    b_rph = round(base_cost / base_hours, 0) if base_hours > 0 else None
    c_rph = round(comp_cost / comp_hours, 0) if comp_hours > 0 else None
    diff_rph = round(c_rph - b_rph, 0) if (b_rph is not None and c_rph is not None) else None

    summary = {
        'base_hours': round(base_hours, 1),
        'compare_hours': round(comp_hours, 1),
        'diff_hours': round(diff_hours, 1),
        'diff_pct': diff_pct,
        'base_cost': int(base_cost),
        'compare_cost': int(comp_cost),
        'base_rev_per_hour': int(b_rph) if b_rph is not None else None,
        'compare_rev_per_hour': int(c_rph) if c_rph is not None else None,
        'diff_rev_per_hour': int(diff_rph) if diff_rph is not None else None,
    }

    # --- カテゴリ別比較（時間制のみ） ---
    def _category_breakdown(start, end):
        rows = db.session.query(
            WorkRecord.category2,
            WorkRecord.work_name,
            func.sum(WorkRecord.quantity).label('qty'),
        ).filter(
            WorkRecord.category1 == department,
            WorkRecord.work_date >= start,
            WorkRecord.work_date <= end,
        ).group_by(WorkRecord.category2, WorkRecord.work_name).all()

        cat_hours = {}
        for cat2, work_name, qty in rows:
            if get_unit_type(work_name) == 'count':
                continue
            display_cat = CategoryMapping.auto_categorize(cat2, work_name)
            cat_hours[display_cat] = cat_hours.get(display_cat, 0) + float(qty or 0)
        return cat_hours

    base_cats = _category_breakdown(base_start, base_end)
    comp_cats = _category_breakdown(comp_start, comp_end)
    all_cats = sorted(set(list(base_cats.keys()) + list(comp_cats.keys())))

    category_breakdown = []
    for cat in all_cats:
        bh = base_cats.get(cat, 0)
        ch = comp_cats.get(cat, 0)
        d = ch - bh
        pct = round(d / bh * 100, 1) if bh > 0 else (0 if d == 0 else None)
        category_breakdown.append({
            'category': cat,
            'base_hours': round(bh, 1),
            'compare_hours': round(ch, 1),
            'diff_hours': round(d, 1),
            'diff_pct': pct,
        })

    # --- スタッフ別比較（時間制のみ） ---
    def _staff_breakdown(start, end):
        rows = db.session.query(
            WorkRecord.staff_name,
            WorkRecord.work_name,
            func.sum(WorkRecord.quantity).label('qty'),
        ).filter(
            WorkRecord.category1 == department,
            WorkRecord.work_date >= start,
            WorkRecord.work_date <= end,
        ).group_by(WorkRecord.staff_name, WorkRecord.work_name).all()

        staff_hours = {}
        for staff_name, work_name, qty in rows:
            if get_unit_type(work_name) == 'count':
                continue
            staff_hours[staff_name] = staff_hours.get(staff_name, 0) + float(qty or 0)
        return staff_hours

    base_staff = _staff_breakdown(base_start, base_end)
    comp_staff = _staff_breakdown(comp_start, comp_end)
    all_staff = sorted(set(list(base_staff.keys()) + list(comp_staff.keys())))

    staff_breakdown = []
    for name in all_staff:
        bh = base_staff.get(name, 0)
        ch = comp_staff.get(name, 0)
        d = ch - bh
        pct = round(d / bh * 100, 1) if bh > 0 else (0 if d == 0 else None)
        staff_breakdown.append({
            'staff_name': name,
            'base_hours': round(bh, 1),
            'compare_hours': round(ch, 1),
            'diff_hours': round(d, 1),
            'diff_pct': pct,
        })

    # --- 業務名別変動TOP ---
    def _work_breakdown(start, end):
        return db.session.query(
            WorkRecord.work_name,
            func.sum(WorkRecord.quantity).label('qty'),
        ).filter(
            WorkRecord.category1 == department,
            WorkRecord.work_date >= start,
            WorkRecord.work_date <= end,
        ).group_by(WorkRecord.work_name).all()

    base_work_rows = _work_breakdown(base_start, base_end)
    comp_work_rows = _work_breakdown(comp_start, comp_end)
    base_work = {r.work_name: float(r.qty or 0) for r in base_work_rows}
    comp_work = {r.work_name: float(r.qty or 0) for r in comp_work_rows}
    all_work = set(list(base_work.keys()) + list(comp_work.keys()))

    work_changes = []
    for name in all_work:
        if not name:
            continue
        bh = base_work.get(name, 0)
        ch = comp_work.get(name, 0)
        d = ch - bh
        pct = round(d / bh * 100, 1) if bh > 0 else (0 if d == 0 else None)
        ut = get_unit_type(name)
        work_changes.append({
            'work_name': name,
            'base_value': round(bh, 1),
            'compare_value': round(ch, 1),
            'diff_value': round(d, 1),
            'diff_pct': pct,
            'abs_diff': round(abs(d), 1),
            'unit_type': ut,
            'unit_suffix': 'h' if ut == 'hours' else '件',
        })

    work_changes.sort(key=lambda x: x['abs_diff'], reverse=True)
    work_changes = work_changes[:30]

    # --- 業務タイプ別比較（時間制のみ） ---
    def _work_type_breakdown(start, end):
        rows = db.session.query(
            WorkRecord.work_name,
            func.sum(WorkRecord.quantity).label('qty'),
        ).filter(
            WorkRecord.category1 == department,
            WorkRecord.work_date >= start,
            WorkRecord.work_date <= end,
        ).group_by(WorkRecord.work_name).all()

        type_hours = {}
        for work_name, qty in rows:
            if get_unit_type(work_name) == 'count':
                continue
            wt = WorkTypeClassification.get_work_type(work_name) or '判断・対応'
            type_hours[wt] = type_hours.get(wt, 0) + float(qty or 0)
        return type_hours

    base_types = _work_type_breakdown(base_start, base_end)
    comp_types = _work_type_breakdown(comp_start, comp_end)
    all_types = WORK_TYPE_CHOICES  # 固定順序

    work_type_breakdown = []
    for wt in all_types:
        bh = base_types.get(wt, 0)
        ch = comp_types.get(wt, 0)
        d = ch - bh
        pct = round(d / bh * 100, 1) if bh > 0 else (0 if d == 0 else None)
        work_type_breakdown.append({
            'work_type': wt,
            'base_hours': round(bh, 1),
            'compare_hours': round(ch, 1),
            'diff_hours': round(d, 1),
            'diff_pct': pct,
        })

    return {
        'department': department,
        'base_month': base_month,
        'compare_month': compare_month,
        'summary': summary,
        'category_breakdown': category_breakdown,
        'staff_breakdown': staff_breakdown,
        'work_changes': work_changes,
        'work_type_breakdown': work_type_breakdown,
    }


@bp.route('/analytics/department-month-comparison')
def get_department_month_comparison():
    """全部門の前月vs今月比較データ"""
    base_month = request.args.get('base_month')
    compare_month = request.args.get('compare_month')

    # 利用可能な月を取得
    is_pg = str(db.engine.url).startswith('postgresql')
    if is_pg:
        month_expr = func.to_char(WorkRecord.work_date, 'YYYY-MM')
    else:
        month_expr = func.strftime('%Y-%m', WorkRecord.work_date)

    month_rows = db.session.query(
        month_expr.label('ym')
    ).distinct().order_by(month_expr.desc()).all()
    available_months = [r.ym for r in month_rows if r.ym]

    # 未指定時は最新2ヶ月を自動選択
    if not compare_month and len(available_months) >= 1:
        compare_month = available_months[0]
    if not base_month and len(available_months) >= 2:
        base_month = available_months[1]

    if not base_month or not compare_month:
        return jsonify({
            'base_month': base_month,
            'compare_month': compare_month,
            'available_months': available_months,
            'departments': [],
        })

    base_start, base_end = _parse_month_range(base_month)
    comp_start, comp_end = _parse_month_range(compare_month)

    # 部門一覧
    dept_query = db.session.query(WorkRecord.category1).distinct()
    departments = [d.category1 for d in dept_query.all() if d.category1]

    default_rate = AppSetting.get_value('default_hourly_rate', 2000)
    hourly_rate = int(request.args.get('hourly_rate', default_rate))

    dept_data = []
    for dept in sorted(departments):
        # 時間制のみ合計（件数制を除外）
        bh, b_count = _sum_hours_only(dept, base_start, base_end)
        ch, c_count = _sum_hours_only(dept, comp_start, comp_end)

        # コスト・スタッフ数は従来通り
        base_cost_row = db.session.query(
            func.coalesce(func.sum(WorkRecord.total_amount), 0),
            func.count(distinct(WorkRecord.staff_name)),
        ).filter(
            WorkRecord.category1 == dept,
            WorkRecord.work_date >= base_start,
            WorkRecord.work_date <= base_end,
        ).first()

        comp_cost_row = db.session.query(
            func.coalesce(func.sum(WorkRecord.total_amount), 0),
            func.count(distinct(WorkRecord.staff_name)),
        ).filter(
            WorkRecord.category1 == dept,
            WorkRecord.work_date >= comp_start,
            WorkRecord.work_date <= comp_end,
        ).first()

        bc = float(base_cost_row[0] or 0)
        cc = float(comp_cost_row[0] or 0)
        diff_h = ch - bh
        diff_c = cc - bc

        # 効率指標
        b_rph = round(bc / bh, 0) if bh > 0 else None
        c_rph = round(cc / ch, 0) if ch > 0 else None
        diff_rph = round(c_rph - b_rph, 0) if (b_rph is not None and c_rph is not None) else None

        dept_data.append({
            'department': dept,
            'base_hours': round(bh, 1),
            'compare_hours': round(ch, 1),
            'diff_hours': round(diff_h, 1),
            'diff_hours_pct': round(diff_h / bh * 100, 1) if bh > 0 else (0 if diff_h == 0 else None),
            'base_count': round(b_count, 1),
            'compare_count': round(c_count, 1),
            'base_cost': int(bc),
            'compare_cost': int(cc),
            'diff_cost': int(diff_c),
            'diff_cost_pct': round(diff_c / bc * 100, 1) if bc > 0 else (0 if diff_c == 0 else None),
            'staff_count_base': base_cost_row[1] or 0,
            'staff_count_compare': comp_cost_row[1] or 0,
            'base_rev_per_hour': int(b_rph) if b_rph is not None else None,
            'compare_rev_per_hour': int(c_rph) if c_rph is not None else None,
            'diff_rev_per_hour': int(diff_rph) if diff_rph is not None else None,
        })

    # 全体（合計）行を先頭に挿入
    if dept_data:
        total_bh = sum(d['base_hours'] for d in dept_data)
        total_ch = sum(d['compare_hours'] for d in dept_data)
        total_bc = sum(d['base_cost'] for d in dept_data)
        total_cc = sum(d['compare_cost'] for d in dept_data)
        total_diff_h = total_ch - total_bh
        total_diff_c = total_cc - total_bc
        total_b_rph = round(total_bc / total_bh, 0) if total_bh > 0 else None
        total_c_rph = round(total_cc / total_ch, 0) if total_ch > 0 else None
        total_diff_rph = round(total_c_rph - total_b_rph, 0) if (total_b_rph is not None and total_c_rph is not None) else None

        total_row = {
            'department': '全体',
            'base_hours': round(total_bh, 1),
            'compare_hours': round(total_ch, 1),
            'diff_hours': round(total_diff_h, 1),
            'diff_hours_pct': round(total_diff_h / total_bh * 100, 1) if total_bh > 0 else 0,
            'base_count': 0,
            'compare_count': 0,
            'base_cost': int(total_bc),
            'compare_cost': int(total_cc),
            'diff_cost': int(total_diff_c),
            'diff_cost_pct': round(total_diff_c / total_bc * 100, 1) if total_bc > 0 else 0,
            'staff_count_base': 0,
            'staff_count_compare': 0,
            'base_rev_per_hour': int(total_b_rph) if total_b_rph is not None else None,
            'compare_rev_per_hour': int(total_c_rph) if total_c_rph is not None else None,
            'diff_rev_per_hour': int(total_diff_rph) if total_diff_rph is not None else None,
            'is_total': True,
        }
        dept_data.insert(0, total_row)

    return jsonify({
        'base_month': base_month,
        'compare_month': compare_month,
        'available_months': available_months,
        'departments': dept_data,
    })


@bp.route('/analytics/department-month-detail')
def get_department_month_detail():
    """個別部門の前月vs今月詳細比較データ"""
    department = request.args.get('department')
    if not department:
        return jsonify({'error': 'department parameter is required'}), 400

    base_month = request.args.get('base_month')
    compare_month = request.args.get('compare_month')

    # 未指定時は最新2ヶ月を自動選択
    if not base_month or not compare_month:
        is_pg = str(db.engine.url).startswith('postgresql')
        if is_pg:
            month_expr = func.to_char(WorkRecord.work_date, 'YYYY-MM')
        else:
            month_expr = func.strftime('%Y-%m', WorkRecord.work_date)
        month_rows = db.session.query(month_expr.label('ym')).distinct().order_by(month_expr.desc()).all()
        months = [r.ym for r in month_rows if r.ym]
        if not compare_month and len(months) >= 1:
            compare_month = months[0]
        if not base_month and len(months) >= 2:
            base_month = months[1]

    if not base_month or not compare_month:
        return jsonify({'error': 'insufficient month data'}), 400

    data = get_department_month_detail_data(department, base_month, compare_month)
    return jsonify(data)


@bp.route('/analytics/department-monthly-trend')
def get_department_monthly_trend():
    """部門の月次推移データ（時間・売上・効率）"""
    department = request.args.get('department')
    if not department:
        return jsonify({'error': 'department parameter is required'}), 400

    month_expr = _month_format_expr()

    # 全体モード: department='全体' の場合は全部門合計
    dept_filter = [] if department == '全体' else [WorkRecord.category1 == department]

    # 月ごと・work_name別に集計（unit_type判定のため）
    rows = db.session.query(
        month_expr.label('ym'),
        WorkRecord.work_name,
        func.sum(WorkRecord.quantity).label('qty'),
    ).filter(
        *dept_filter,
    ).group_by(month_expr, WorkRecord.work_name).all()

    # 月ごとに時間制のみ合計
    month_hours = {}
    for ym, work_name, qty in rows:
        if not ym:
            continue
        if get_unit_type(work_name) == 'count':
            continue
        month_hours[ym] = month_hours.get(ym, 0) + float(qty or 0)

    # 月ごとの売上（total_amount合計）
    rev_rows = db.session.query(
        month_expr.label('ym'),
        func.coalesce(func.sum(WorkRecord.total_amount), 0).label('rev'),
    ).filter(
        *dept_filter,
    ).group_by(month_expr).all()

    month_revenue = {r.ym: float(r.rev) for r in rev_rows if r.ym}

    # 時系列ソート（時間 or 売上のある月を全て含む）
    all_months = sorted(set(list(month_hours.keys()) + list(month_revenue.keys())))

    # 時間あたり売上 + 累積売上
    hours_list = []
    revenue_list = []
    rev_per_hour_list = []
    cumulative_rev = 0
    cumulative_list = []

    for m in all_months:
        h = round(month_hours.get(m, 0), 1)
        r = int(month_revenue.get(m, 0))
        rph = int(round(r / h, 0)) if h > 0 else None
        cumulative_rev += r

        hours_list.append(h)
        revenue_list.append(r)
        rev_per_hour_list.append(rph)
        cumulative_list.append(cumulative_rev)

    return jsonify({
        'department': department,
        'months': all_months,
        'hours': hours_list,
        'revenue': revenue_list,
        'rev_per_hour': rev_per_hour_list,
        'cumulative_revenue': cumulative_list,
    })
