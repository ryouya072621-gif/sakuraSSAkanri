import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from config import Config

db = SQLAlchemy()


def init_default_data():
    """初期データを投入"""
    from app.models import DisplayCategory, CategoryKeyword, AppSetting

    # カテゴリが既に存在する場合はスキップ
    if DisplayCategory.query.first():
        return

    # デフォルトカテゴリ（value_rank: S=高価値, A=中価値, B=低価値, C=無駄）
    categories_data = [
        {'name': 'コア業務', 'color': '#3B82F6', 'badge_bg_color': '#dbeafe', 'badge_text_color': '#1d4ed8', 'is_reduction_target': False, 'value_rank': 'S', 'sort_order': 1},
        {'name': 'MTG', 'color': '#8B5CF6', 'badge_bg_color': '#ede9fe', 'badge_text_color': '#6d28d9', 'is_reduction_target': False, 'value_rank': 'A', 'sort_order': 2},
        {'name': '事務', 'color': '#6B7280', 'badge_bg_color': '#f3f4f6', 'badge_text_color': '#374151', 'is_reduction_target': False, 'value_rank': 'A', 'sort_order': 3},
        {'name': 'その他', 'color': '#EF4444', 'badge_bg_color': '#fee2e2', 'badge_text_color': '#dc2626', 'is_reduction_target': True, 'value_rank': 'B', 'sort_order': 4},
        {'name': '移動', 'color': '#F97316', 'badge_bg_color': '#ffedd5', 'badge_text_color': '#ea580c', 'is_reduction_target': True, 'value_rank': 'C', 'sort_order': 5},
    ]

    categories = {}
    for cat_data in categories_data:
        cat = DisplayCategory(**cat_data)
        db.session.add(cat)
        categories[cat_data['name']] = cat

    db.session.flush()  # IDを確定

    # デフォルトキーワード（優先度順にマッチング）
    keywords_data = [
        # MTG（優先度: 30）- 明確に判別可能
        {'keyword': 'mtg', 'category': 'MTG', 'priority': 30},
        {'keyword': '面談', 'category': 'MTG', 'priority': 30},
        {'keyword': '打ち合わせ', 'category': 'MTG', 'priority': 30},
        {'keyword': '会議', 'category': 'MTG', 'priority': 30},
        {'keyword': 'ミーティング', 'category': 'MTG', 'priority': 30},
        # 移動（優先度: 25）- 「移動」という文字列は明確
        {'keyword': '移動', 'category': '移動', 'priority': 25},
        {'keyword': '出張', 'category': '移動', 'priority': 25},
        # コア業務（優先度: 20）- 営業・電話対応はコア業務
        {'keyword': '営業', 'category': 'コア業務', 'priority': 20},
        {'keyword': '電話', 'category': 'コア業務', 'priority': 20},
        {'keyword': 'tel', 'category': 'コア業務', 'priority': 20},
        # コア業務（優先度: 15）- 〇〇対応はコア業務
        {'keyword': '対応', 'category': 'コア業務', 'priority': 15},
        # 事務（優先度: 15）- 汎用的なので低め
        {'keyword': '事務', 'category': '事務', 'priority': 15},
        {'keyword': 'チェック', 'category': '事務', 'priority': 15},
        {'keyword': '確認', 'category': '事務', 'priority': 15},
        {'keyword': '集計', 'category': '事務', 'priority': 15},
        {'keyword': '入力', 'category': '事務', 'priority': 15},
        # その他（優先度: 5）- 最後の手段
        {'keyword': 'その他', 'category': 'その他', 'priority': 5},
        {'keyword': '雑務', 'category': 'その他', 'priority': 5},
        {'keyword': '待機', 'category': 'その他', 'priority': 5},
        {'keyword': '不明', 'category': 'その他', 'priority': 5},
    ]

    for kw_data in keywords_data:
        kw = CategoryKeyword(
            keyword=kw_data['keyword'],
            display_category_id=categories[kw_data['category']].id,
            match_type='contains',
            priority=kw_data['priority'],
            is_active=True
        )
        db.session.add(kw)

    # デフォルト設定
    settings_data = [
        {'key': 'default_hourly_rate', 'value': '2000', 'value_type': 'int', 'description': 'デフォルト時給（円）'},
        {'key': 'ranking_limit', 'value': '10', 'value_type': 'int', 'description': 'ランキング表示件数'},
        {'key': 'default_category', 'value': 'コア業務', 'value_type': 'string', 'description': 'デフォルト分類カテゴリ'},
    ]

    for setting_data in settings_data:
        setting = AppSetting(**setting_data)
        db.session.add(setting)

    db.session.commit()


def _migrate_value_rank():
    """既存DBにvalue_rankカラムがなければ追加"""
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    columns = [c['name'] for c in inspector.get_columns('display_categories')]
    if 'value_rank' not in columns:
        db.session.execute(text("ALTER TABLE display_categories ADD COLUMN value_rank VARCHAR(1) DEFAULT 'A'"))
        # デフォルト値を設定: 削減対象はB/C、それ以外はA、コア業務はS
        db.session.execute(text("UPDATE display_categories SET value_rank = 'S' WHERE name = 'コア業務'"))
        db.session.execute(text("UPDATE display_categories SET value_rank = 'C' WHERE name = '移動'"))
        # is_reduction_target: PostgreSQLはbool型、SQLiteはint型なので両対応
        is_pg = str(db.engine.url).startswith('postgresql')
        if is_pg:
            db.session.execute(text("UPDATE display_categories SET value_rank = 'B' WHERE is_reduction_target = true AND value_rank = 'A'"))
        else:
            db.session.execute(text("UPDATE display_categories SET value_rank = 'B' WHERE is_reduction_target = 1 AND value_rank = 'A'"))
        db.session.commit()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)

    from app.routes import main, upload, api, admin, ai
    app.register_blueprint(main.bp)
    app.register_blueprint(upload.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(ai.bp)

    with app.app_context():
        db.create_all()
        _migrate_value_rank()
        init_default_data()

    return app
