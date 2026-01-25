from datetime import datetime
from app import db


class DisplayCategory(db.Model):
    """表示カテゴリマスタ"""
    __tablename__ = 'display_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(7), default='#6B7280')
    badge_bg_color = db.Column(db.String(7), default='#f3f4f6')
    badge_text_color = db.Column(db.String(7), default='#374151')
    is_reduction_target = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    keywords = db.relationship('CategoryKeyword', backref='display_category', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'color': self.color,
            'badge_bg_color': self.badge_bg_color,
            'badge_text_color': self.badge_text_color,
            'is_reduction_target': self.is_reduction_target,
            'sort_order': self.sort_order,
            'keyword_count': self.keywords.count()
        }


class CategoryKeyword(db.Model):
    """キーワード分類ルール"""
    __tablename__ = 'category_keywords'

    id = db.Column(db.Integer, primary_key=True)
    keyword = db.Column(db.String(100), nullable=False)
    display_category_id = db.Column(db.Integer, db.ForeignKey('display_categories.id'), nullable=False)
    match_type = db.Column(db.String(20), default='contains')  # contains, exact, startswith
    priority = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'keyword': self.keyword,
            'display_category_id': self.display_category_id,
            'display_category_name': self.display_category.name if self.display_category else None,
            'match_type': self.match_type,
            'priority': self.priority,
            'is_active': self.is_active
        }


class AppSetting(db.Model):
    """アプリケーション設定"""
    __tablename__ = 'app_settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    value_type = db.Column(db.String(20), default='string')  # string, int, float, bool
    description = db.Column(db.String(255))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get_value(key, default=None):
        """設定値を取得"""
        setting = AppSetting.query.filter_by(key=key).first()
        if not setting:
            return default
        if setting.value_type == 'int':
            return int(setting.value)
        if setting.value_type == 'float':
            return float(setting.value)
        if setting.value_type == 'bool':
            return setting.value.lower() in ('true', '1', 'yes')
        return setting.value

    @staticmethod
    def set_value(key, value, value_type='string', description=None):
        """設定値を保存"""
        setting = AppSetting.query.filter_by(key=key).first()
        if setting:
            setting.value = str(value)
            if value_type:
                setting.value_type = value_type
            if description:
                setting.description = description
        else:
            setting = AppSetting(
                key=key,
                value=str(value),
                value_type=value_type,
                description=description
            )
            db.session.add(setting)
        db.session.commit()
        return setting


class WorkRecord(db.Model):
    """業務記録"""
    __tablename__ = 'work_records'

    id = db.Column(db.Integer, primary_key=True)
    work_date = db.Column(db.Date, nullable=False)
    staff_name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100))
    category1 = db.Column(db.String(100))
    category2 = db.Column(db.String(100))
    work_name = db.Column(db.String(500))
    unit_price = db.Column(db.Integer, default=0)
    quantity = db.Column(db.Integer, default=0)
    total_amount = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20))
    source_month = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('idx_work_date', 'work_date'),
        db.Index('idx_staff_name', 'staff_name'),
        db.Index('idx_staff_date', 'staff_name', 'work_date'),
    )


class CategoryMapping(db.Model):
    """カテゴリマッピング"""
    __tablename__ = 'category_mapping'

    id = db.Column(db.Integer, primary_key=True)
    source_category = db.Column(db.String(100), unique=True)
    display_category = db.Column(db.String(50), default='その他')
    is_reduction_target = db.Column(db.Boolean, default=False)

    # キャッシュ用クラス変数
    _keyword_cache = None
    _reduction_cache = None
    _default_category_cache = None

    @classmethod
    def clear_cache(cls):
        """キャッシュをクリア"""
        cls._keyword_cache = None
        cls._reduction_cache = None
        cls._default_category_cache = None

    @classmethod
    def get_cached_keywords(cls):
        """キーワードをキャッシュから取得（一度だけDBアクセス）"""
        if cls._keyword_cache is None:
            keywords = CategoryKeyword.query.filter_by(is_active=True)\
                .order_by(CategoryKeyword.priority.desc()).all()
            cls._keyword_cache = [
                {
                    'keyword': kw.keyword.lower(),
                    'match_type': kw.match_type,
                    'category_name': kw.display_category.name
                }
                for kw in keywords
            ]
        return cls._keyword_cache

    @classmethod
    def get_cached_reduction_targets(cls):
        """削減対象カテゴリをキャッシュから取得"""
        if cls._reduction_cache is None:
            categories = DisplayCategory.query.filter_by(is_reduction_target=True).all()
            cls._reduction_cache = {c.name for c in categories}
        return cls._reduction_cache

    @classmethod
    def get_cached_default_category(cls):
        """デフォルトカテゴリをキャッシュから取得"""
        if cls._default_category_cache is None:
            cls._default_category_cache = AppSetting.get_value('default_category', 'コア業務')
        return cls._default_category_cache

    @staticmethod
    def get_display_category(source_cat):
        """元カテゴリから表示カテゴリを取得"""
        if not source_cat:
            return 'その他'
        mapping = CategoryMapping.query.filter_by(source_category=source_cat).first()
        if mapping:
            return mapping.display_category
        return CategoryMapping.auto_categorize(source_cat)

    @classmethod
    def auto_categorize(cls, source_cat, work_name=None):
        """キーワードベースの自動分類（キャッシュ使用）

        category2とwork_nameの両方でキーワードマッチングを行う
        """
        keywords = cls.get_cached_keywords()

        # マッチング対象テキストのリストを作成
        texts_to_check = []
        if source_cat:
            texts_to_check.append(source_cat.lower())
        if work_name:
            texts_to_check.append(work_name.lower())

        if not texts_to_check:
            return cls.get_cached_default_category()

        # 各キーワードで両方のテキストをチェック
        for kw in keywords:
            for text in texts_to_check:
                if kw['match_type'] == 'exact' and text == kw['keyword']:
                    return kw['category_name']
                elif kw['match_type'] == 'startswith' and text.startswith(kw['keyword']):
                    return kw['category_name']
                elif kw['match_type'] == 'contains' and kw['keyword'] in text:
                    return kw['category_name']

        return cls.get_cached_default_category()

    @classmethod
    def is_target_for_reduction(cls, display_cat):
        """削減対象かどうか（キャッシュ使用）"""
        return display_cat in cls.get_cached_reduction_targets()
