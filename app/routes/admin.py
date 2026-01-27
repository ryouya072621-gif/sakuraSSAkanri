from flask import Blueprint, render_template, jsonify, request
from sqlalchemy import func
from app import db
from app.models import DisplayCategory, CategoryKeyword, AppSetting, WorkRecord, CategoryMapping, UnitTypeRule, SubCategoryRule

bp = Blueprint('admin', __name__, url_prefix='/admin')


# ページルート
@bp.route('/')
def index():
    """管理画面トップ"""
    categories_count = DisplayCategory.query.count()
    keywords_count = CategoryKeyword.query.count()
    reduction_count = DisplayCategory.query.filter_by(is_reduction_target=True).count()

    settings = {
        'default_hourly_rate': AppSetting.get_value('default_hourly_rate', 2000),
        'ranking_limit': AppSetting.get_value('ranking_limit', 10),
        'default_category': AppSetting.get_value('default_category', 'コア業務'),
    }

    return render_template('admin/index.html',
                           categories_count=categories_count,
                           keywords_count=keywords_count,
                           reduction_count=reduction_count,
                           settings=settings)


@bp.route('/categories')
def categories():
    """カテゴリ管理画面"""
    return render_template('admin/categories.html')


@bp.route('/keywords')
def keywords():
    """キーワード管理画面"""
    categories = DisplayCategory.query.order_by(DisplayCategory.sort_order).all()
    return render_template('admin/keywords.html', categories=categories)


@bp.route('/settings')
def settings():
    """設定画面"""
    categories = DisplayCategory.query.order_by(DisplayCategory.sort_order).all()
    return render_template('admin/settings.html', categories=categories)


# カテゴリAPI
@bp.route('/api/categories', methods=['GET'])
def api_get_categories():
    """カテゴリ一覧取得"""
    categories = DisplayCategory.query.order_by(DisplayCategory.sort_order).all()
    return jsonify({
        'categories': [cat.to_dict() for cat in categories]
    })


@bp.route('/api/categories', methods=['POST'])
def api_create_category():
    """カテゴリ作成"""
    data = request.json

    # 既存チェック
    if DisplayCategory.query.filter_by(name=data['name']).first():
        return jsonify({'success': False, 'error': '同名のカテゴリが既に存在します'}), 400

    # 最大sort_orderを取得
    max_order = db.session.query(db.func.max(DisplayCategory.sort_order)).scalar() or 0

    category = DisplayCategory(
        name=data['name'],
        color=data.get('color', '#6B7280'),
        badge_bg_color=data.get('badge_bg_color', '#f3f4f6'),
        badge_text_color=data.get('badge_text_color', '#374151'),
        is_reduction_target=data.get('is_reduction_target', False),
        sort_order=max_order + 1
    )
    db.session.add(category)
    db.session.commit()

    return jsonify({'success': True, 'category': category.to_dict()})


@bp.route('/api/categories/<int:id>', methods=['PUT'])
def api_update_category(id):
    """カテゴリ更新"""
    category = DisplayCategory.query.get_or_404(id)
    data = request.json

    # 名前変更時の重複チェック
    if 'name' in data and data['name'] != category.name:
        if DisplayCategory.query.filter_by(name=data['name']).first():
            return jsonify({'success': False, 'error': '同名のカテゴリが既に存在します'}), 400

    category.name = data.get('name', category.name)
    category.color = data.get('color', category.color)
    category.badge_bg_color = data.get('badge_bg_color', category.badge_bg_color)
    category.badge_text_color = data.get('badge_text_color', category.badge_text_color)
    category.is_reduction_target = data.get('is_reduction_target', category.is_reduction_target)

    db.session.commit()

    return jsonify({'success': True, 'category': category.to_dict()})


@bp.route('/api/categories/<int:id>', methods=['DELETE'])
def api_delete_category(id):
    """カテゴリ削除"""
    category = DisplayCategory.query.get_or_404(id)

    # 紐付くキーワードがある場合は警告
    if category.keywords.count() > 0:
        return jsonify({
            'success': False,
            'error': f'このカテゴリには{category.keywords.count()}件のキーワードが紐付いています。先にキーワードを削除してください。'
        }), 400

    db.session.delete(category)
    db.session.commit()

    return jsonify({'success': True})


@bp.route('/api/categories/order', methods=['PUT'])
def api_update_category_order():
    """カテゴリ順序更新"""
    data = request.json
    order = data.get('order', [])

    for i, cat_id in enumerate(order):
        category = DisplayCategory.query.get(cat_id)
        if category:
            category.sort_order = i + 1

    db.session.commit()

    return jsonify({'success': True})


# キーワードAPI
@bp.route('/api/keywords', methods=['GET'])
def api_get_keywords():
    """キーワード一覧取得"""
    category_id = request.args.get('category_id', type=int)
    active_only = request.args.get('active_only', 'false').lower() == 'true'

    query = CategoryKeyword.query

    if category_id:
        query = query.filter_by(display_category_id=category_id)
    if active_only:
        query = query.filter_by(is_active=True)

    keywords = query.order_by(CategoryKeyword.priority.desc(), CategoryKeyword.keyword).all()

    return jsonify({
        'keywords': [kw.to_dict() for kw in keywords]
    })


@bp.route('/api/keywords', methods=['POST'])
def api_create_keyword():
    """キーワード作成"""
    data = request.json

    keyword = CategoryKeyword(
        keyword=data['keyword'],
        display_category_id=data['display_category_id'],
        match_type=data.get('match_type', 'contains'),
        priority=data.get('priority', 0),
        is_active=data.get('is_active', True)
    )
    db.session.add(keyword)
    db.session.commit()

    return jsonify({'success': True, 'keyword': keyword.to_dict()})


@bp.route('/api/keywords/<int:id>', methods=['PUT'])
def api_update_keyword(id):
    """キーワード更新"""
    keyword = CategoryKeyword.query.get_or_404(id)
    data = request.json

    keyword.keyword = data.get('keyword', keyword.keyword)
    keyword.display_category_id = data.get('display_category_id', keyword.display_category_id)
    keyword.match_type = data.get('match_type', keyword.match_type)
    keyword.priority = data.get('priority', keyword.priority)
    keyword.is_active = data.get('is_active', keyword.is_active)

    db.session.commit()

    return jsonify({'success': True, 'keyword': keyword.to_dict()})


@bp.route('/api/keywords/<int:id>', methods=['DELETE'])
def api_delete_keyword(id):
    """キーワード削除"""
    keyword = CategoryKeyword.query.get_or_404(id)
    db.session.delete(keyword)
    db.session.commit()

    return jsonify({'success': True})


# 設定API
@bp.route('/api/settings', methods=['GET'])
def api_get_settings():
    """設定一覧取得"""
    settings = AppSetting.query.all()
    return jsonify({
        'settings': {s.key: {'value': s.value, 'type': s.value_type, 'description': s.description} for s in settings}
    })


@bp.route('/api/settings', methods=['PUT'])
def api_update_settings():
    """設定一括更新"""
    data = request.json

    for key, value in data.items():
        setting = AppSetting.query.filter_by(key=key).first()
        if setting:
            setting.value = str(value)
        else:
            # 新規設定の場合
            setting = AppSetting(key=key, value=str(value))
            db.session.add(setting)

    db.session.commit()

    return jsonify({'success': True})


# 自動キーワード提案API
@bp.route('/api/suggest-keywords', methods=['GET'])
def api_suggest_keywords():
    """未分類データを分析してキーワード候補を提案"""
    # キャッシュをクリアして最新状態を取得
    CategoryMapping.clear_cache()

    # 提案パターン（キーワード、提案カテゴリ）
    suggest_patterns = [
        ('mtg', 'MTG'),
        ('面談', 'MTG'),
        ('打合せ', 'MTG'),
        ('打ち合わせ', 'MTG'),
        ('会議', 'MTG'),
        ('ミーティング', 'MTG'),
        ('移動', '移動'),
        ('出張', '移動'),
        ('営業', 'コア業務'),
        ('電話', 'コア業務'),
        ('tel', 'コア業務'),
        ('対応', 'コア業務'),
        ('事務', '事務'),
        ('入力', '事務'),
        ('チェック', '事務'),
        ('確認', '事務'),
        ('集計', '事務'),
        ('報告', '事務'),
        ('その他', 'その他'),
        ('雑務', 'その他'),
        ('待機', 'その他'),
    ]

    # 既存キーワードを取得
    existing_keywords = {kw.keyword.lower() for kw in CategoryKeyword.query.all()}

    suggestions = []
    default_category = CategoryMapping.get_cached_default_category()

    for keyword, suggested_category in suggest_patterns:
        # 既に登録済みのキーワードはスキップ
        if keyword.lower() in existing_keywords:
            continue

        # work_nameまたはcategory2にこのキーワードを含むレコードを集計
        count = WorkRecord.query.filter(
            db.or_(
                func.lower(WorkRecord.work_name).contains(keyword.lower()),
                func.lower(WorkRecord.category2).contains(keyword.lower())
            )
        ).count()

        if count > 0:
            # 現在このキーワードがどのカテゴリに分類されているか確認
            sample = WorkRecord.query.filter(
                db.or_(
                    func.lower(WorkRecord.work_name).contains(keyword.lower()),
                    func.lower(WorkRecord.category2).contains(keyword.lower())
                )
            ).first()

            current_category = CategoryMapping.auto_categorize(
                sample.category2, sample.work_name
            ) if sample else default_category

            # デフォルトカテゴリに分類されている（＝未分類）場合のみ提案
            if current_category == default_category:
                suggestions.append({
                    'keyword': keyword,
                    'suggested_category': suggested_category,
                    'match_count': count,
                    'current_category': current_category
                })

    # マッチ数でソート
    suggestions.sort(key=lambda x: x['match_count'], reverse=True)

    # カテゴリ一覧も返す
    categories = DisplayCategory.query.order_by(DisplayCategory.sort_order).all()

    return jsonify({
        'suggestions': suggestions,
        'categories': [{'id': c.id, 'name': c.name} for c in categories]
    })


@bp.route('/api/apply-suggestions', methods=['POST'])
def api_apply_suggestions():
    """提案されたキーワードを一括登録"""
    data = request.json
    keywords_to_add = data.get('keywords', [])

    added = []
    for kw_data in keywords_to_add:
        # カテゴリIDを取得
        category = DisplayCategory.query.filter_by(name=kw_data['category']).first()
        if not category:
            continue

        # 既存チェック
        existing = CategoryKeyword.query.filter_by(keyword=kw_data['keyword']).first()
        if existing:
            continue

        keyword = CategoryKeyword(
            keyword=kw_data['keyword'],
            display_category_id=category.id,
            match_type='contains',
            priority=10,
            is_active=True
        )
        db.session.add(keyword)
        added.append(kw_data['keyword'])

    db.session.commit()

    # キャッシュをクリア
    CategoryMapping.clear_cache()

    return jsonify({
        'success': True,
        'added_count': len(added),
        'added_keywords': added
    })


# ============================================
# 単位タイプルール管理
# ============================================

@bp.route('/unit-rules')
def unit_rules():
    """単位タイプルール管理画面"""
    return render_template('admin/unit_rules.html')


@bp.route('/api/unit-rules', methods=['GET'])
def api_get_unit_rules():
    """単位タイプルール一覧取得"""
    rules = UnitTypeRule.query.order_by(UnitTypeRule.priority.desc(), UnitTypeRule.keyword).all()
    return jsonify({
        'rules': [r.to_dict() for r in rules]
    })


@bp.route('/api/unit-rules', methods=['POST'])
def api_create_unit_rule():
    """単位タイプルール作成"""
    data = request.json

    rule = UnitTypeRule(
        keyword=data['keyword'],
        unit_type=data.get('unit_type', 'hours'),
        match_type=data.get('match_type', 'suffix'),
        priority=data.get('priority', 10),
        is_active=data.get('is_active', True)
    )
    db.session.add(rule)
    db.session.commit()
    UnitTypeRule.clear_cache()

    return jsonify({'success': True, 'rule': rule.to_dict()})


@bp.route('/api/unit-rules/<int:id>', methods=['PUT'])
def api_update_unit_rule(id):
    """単位タイプルール更新"""
    rule = UnitTypeRule.query.get_or_404(id)
    data = request.json

    rule.keyword = data.get('keyword', rule.keyword)
    rule.unit_type = data.get('unit_type', rule.unit_type)
    rule.match_type = data.get('match_type', rule.match_type)
    rule.priority = data.get('priority', rule.priority)
    rule.is_active = data.get('is_active', rule.is_active)

    db.session.commit()
    UnitTypeRule.clear_cache()

    return jsonify({'success': True, 'rule': rule.to_dict()})


@bp.route('/api/unit-rules/<int:id>', methods=['DELETE'])
def api_delete_unit_rule(id):
    """単位タイプルール削除"""
    rule = UnitTypeRule.query.get_or_404(id)
    db.session.delete(rule)
    db.session.commit()
    UnitTypeRule.clear_cache()

    return jsonify({'success': True})


@bp.route('/api/unit-rules/seed', methods=['POST'])
def api_seed_unit_rules():
    """デフォルト単位タイプルールを投入"""
    UnitTypeRule.seed_default_rules()
    return jsonify({'success': True, 'message': 'デフォルトルールを投入しました'})


@bp.route('/api/unit-rules/test', methods=['POST'])
def api_test_unit_rule():
    """業務名で単位タイプをテスト"""
    from app.services.task_grouper import get_unit_type, get_unit_suffix

    data = request.json
    work_name = data.get('work_name', '')

    unit_type = get_unit_type(work_name)
    unit_suffix = get_unit_suffix(work_name)

    return jsonify({
        'work_name': work_name,
        'unit_type': unit_type,
        'unit_suffix': unit_suffix,
        'display': f'{work_name} → {unit_suffix}'
    })


# ============================================
# サブカテゴリルール管理
# ============================================

@bp.route('/sub-categories')
def sub_categories():
    """サブカテゴリルール管理画面"""
    categories = DisplayCategory.query.order_by(DisplayCategory.sort_order).all()
    return render_template('admin/sub_categories.html', categories=categories)


@bp.route('/api/sub-categories', methods=['GET'])
def api_get_sub_category_rules():
    """サブカテゴリルール一覧取得"""
    rules = SubCategoryRule.query.order_by(SubCategoryRule.priority.desc(), SubCategoryRule.keyword).all()
    return jsonify({
        'rules': [r.to_dict() for r in rules]
    })


@bp.route('/api/sub-categories', methods=['POST'])
def api_create_sub_category_rule():
    """サブカテゴリルール作成"""
    data = request.json

    rule = SubCategoryRule(
        parent_category_id=data.get('parent_category_id'),
        sub_category_name=data['sub_category_name'],
        keyword=data['keyword'],
        match_type=data.get('match_type', 'contains'),
        priority=data.get('priority', 10),
        is_active=data.get('is_active', True)
    )
    db.session.add(rule)
    db.session.commit()
    SubCategoryRule.clear_cache()

    return jsonify({'success': True, 'rule': rule.to_dict()})


@bp.route('/api/sub-categories/<int:id>', methods=['PUT'])
def api_update_sub_category_rule(id):
    """サブカテゴリルール更新"""
    rule = SubCategoryRule.query.get_or_404(id)
    data = request.json

    rule.parent_category_id = data.get('parent_category_id', rule.parent_category_id)
    rule.sub_category_name = data.get('sub_category_name', rule.sub_category_name)
    rule.keyword = data.get('keyword', rule.keyword)
    rule.match_type = data.get('match_type', rule.match_type)
    rule.priority = data.get('priority', rule.priority)
    rule.is_active = data.get('is_active', rule.is_active)

    db.session.commit()
    SubCategoryRule.clear_cache()

    return jsonify({'success': True, 'rule': rule.to_dict()})


@bp.route('/api/sub-categories/<int:id>', methods=['DELETE'])
def api_delete_sub_category_rule(id):
    """サブカテゴリルール削除"""
    rule = SubCategoryRule.query.get_or_404(id)
    db.session.delete(rule)
    db.session.commit()
    SubCategoryRule.clear_cache()

    return jsonify({'success': True})


@bp.route('/api/sub-categories/seed', methods=['POST'])
def api_seed_sub_category_rules():
    """デフォルトサブカテゴリルールを投入"""
    SubCategoryRule.seed_default_rules()
    return jsonify({'success': True, 'message': 'デフォルトルールを投入しました'})


@bp.route('/api/sub-categories/test', methods=['POST'])
def api_test_sub_category():
    """業務名でサブカテゴリをテスト"""
    from app.services.task_grouper import get_sub_category

    data = request.json
    work_name = data.get('work_name', '')

    sub_category = get_sub_category(work_name)

    return jsonify({
        'work_name': work_name,
        'sub_category': sub_category or '(なし)'
    })
