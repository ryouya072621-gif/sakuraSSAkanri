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


class TaskReductionTarget(db.Model):
    """業務名別の削減対象フラグ"""
    __tablename__ = 'task_reduction_targets'

    id = db.Column(db.Integer, primary_key=True)
    work_name = db.Column(db.String(500), unique=True, nullable=False)
    is_reduction_target = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # キャッシュ用クラス変数
    _cache = None

    @classmethod
    def clear_cache(cls):
        """キャッシュをクリア"""
        cls._cache = None

    @classmethod
    def get_cached_targets(cls):
        """削減対象の業務名をキャッシュから取得"""
        if cls._cache is None:
            targets = cls.query.filter_by(is_reduction_target=True).all()
            cls._cache = {t.work_name for t in targets}
        return cls._cache

    @classmethod
    def is_work_reduction_target(cls, work_name):
        """業務名が削減対象かどうか"""
        if not work_name:
            return False
        return work_name in cls.get_cached_targets()

    @classmethod
    def toggle_target(cls, work_name):
        """削減対象フラグをトグル"""
        target = cls.query.filter_by(work_name=work_name).first()
        if target:
            target.is_reduction_target = not target.is_reduction_target
        else:
            target = cls(work_name=work_name, is_reduction_target=True)
            db.session.add(target)
        db.session.commit()
        cls.clear_cache()
        return target.is_reduction_target

    @classmethod
    def set_as_target(cls, work_name):
        """業務名を削減対象に設定"""
        target = cls.query.filter_by(work_name=work_name).first()
        if target:
            target.is_reduction_target = True
        else:
            target = cls(work_name=work_name, is_reduction_target=True)
            db.session.add(target)
        db.session.commit()
        cls.clear_cache()

    @classmethod
    def remove_from_target(cls, work_name):
        """業務名を削減対象から解除"""
        target = cls.query.filter_by(work_name=work_name).first()
        if target:
            target.is_reduction_target = False
            db.session.commit()
            cls.clear_cache()

    @classmethod
    def bulk_set_targets(cls, work_names, is_target=True):
        """複数の業務名を一括で削減対象に設定/解除"""
        for work_name in work_names:
            target = cls.query.filter_by(work_name=work_name).first()
            if target:
                target.is_reduction_target = is_target
            else:
                target = cls(work_name=work_name, is_reduction_target=is_target)
                db.session.add(target)
        db.session.commit()
        cls.clear_cache()


class ReductionGoal(db.Model):
    """削減目標設定"""
    __tablename__ = 'reduction_goals'

    id = db.Column(db.Integer, primary_key=True)
    goal_type = db.Column(db.String(20), default='global')  # global, category, staff
    target_percent = db.Column(db.Float, default=20.0)
    baseline_hours = db.Column(db.Float, nullable=True)
    baseline_period_start = db.Column(db.Date, nullable=True)
    baseline_period_end = db.Column(db.Date, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('display_categories.id'), nullable=True)
    staff_name = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = db.relationship('DisplayCategory', backref='reduction_goals')

    def to_dict(self):
        return {
            'id': self.id,
            'goal_type': self.goal_type,
            'target_percent': self.target_percent,
            'baseline_hours': self.baseline_hours,
            'baseline_period_start': self.baseline_period_start.strftime('%Y-%m-%d') if self.baseline_period_start else None,
            'baseline_period_end': self.baseline_period_end.strftime('%Y-%m-%d') if self.baseline_period_end else None,
            'category_id': self.category_id,
            'category_name': self.category.name if self.category else None,
            'staff_name': self.staff_name,
            'is_active': self.is_active
        }


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


# ============================================
# AI機能関連モデル
# ============================================

class AICategorySuggestion(db.Model):
    """AIによるカテゴリ提案"""
    __tablename__ = 'ai_category_suggestions'

    id = db.Column(db.Integer, primary_key=True)
    work_record_id = db.Column(db.Integer, db.ForeignKey('work_records.id'), nullable=True)
    category1 = db.Column(db.String(100))
    category2 = db.Column(db.String(100))
    work_name = db.Column(db.String(500))
    suggested_category_id = db.Column(db.Integer, db.ForeignKey('display_categories.id'))
    confidence_score = db.Column(db.Float, default=0.0)  # 0.0-1.0
    reasoning = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')  # pending, accepted, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)

    work_record = db.relationship('WorkRecord', backref='ai_suggestions')
    suggested_category = db.relationship('DisplayCategory')

    def to_dict(self):
        return {
            'id': self.id,
            'work_record_id': self.work_record_id,
            'category1': self.category1,
            'category2': self.category2,
            'work_name': self.work_name,
            'suggested_category_id': self.suggested_category_id,
            'suggested_category_name': self.suggested_category.name if self.suggested_category else None,
            'confidence_score': self.confidence_score,
            'reasoning': self.reasoning,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class AIInsightCache(db.Model):
    """AIインサイトのキャッシュ"""
    __tablename__ = 'ai_insight_cache'

    id = db.Column(db.Integer, primary_key=True)
    cache_key = db.Column(db.String(255), unique=True, nullable=False)
    insight_type = db.Column(db.String(50))  # dashboard, comparison, etc.
    content = db.Column(db.Text)  # JSON string
    expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @classmethod
    def get_cached(cls, cache_key):
        """キャッシュを取得（有効期限チェック付き）"""
        cache = cls.query.filter_by(cache_key=cache_key).first()
        if cache and cache.expires_at > datetime.utcnow():
            import json
            return json.loads(cache.content)
        return None

    @classmethod
    def set_cache(cls, cache_key, insight_type, content, expires_hours=1):
        """キャッシュを設定"""
        import json
        from datetime import timedelta

        # 既存のキャッシュを削除
        cls.query.filter_by(cache_key=cache_key).delete()

        cache = cls(
            cache_key=cache_key,
            insight_type=insight_type,
            content=json.dumps(content, ensure_ascii=False),
            expires_at=datetime.utcnow() + timedelta(hours=expires_hours)
        )
        db.session.add(cache)
        db.session.commit()
        return cache


class AIRequestLog(db.Model):
    """AIリクエストログ（コスト追跡用）"""
    __tablename__ = 'ai_request_logs'

    id = db.Column(db.Integer, primary_key=True)
    request_type = db.Column(db.String(50))  # categorization, insight, chat, report
    input_tokens = db.Column(db.Integer, default=0)
    output_tokens = db.Column(db.Integer, default=0)
    model_used = db.Column(db.String(50))
    cost_estimate = db.Column(db.Float, default=0.0)
    cached = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @classmethod
    def log_request(cls, request_type, input_tokens=0, output_tokens=0, model='', cached=False):
        """リクエストをログに記録"""
        # Claude Sonnet の料金: $3/1M input, $15/1M output
        cost = (input_tokens * 3 / 1_000_000) + (output_tokens * 15 / 1_000_000)

        log = cls(
            request_type=request_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_used=model,
            cost_estimate=cost,
            cached=cached
        )
        db.session.add(log)
        db.session.commit()
        return log


# ============================================
# 単位タイプ・サブカテゴリ関連モデル
# ============================================

class UnitTypeRule(db.Model):
    """単位タイプ判定ルール（時間制 vs 件数制）"""
    __tablename__ = 'unit_type_rules'

    id = db.Column(db.Integer, primary_key=True)
    keyword = db.Column(db.String(100), nullable=False)
    unit_type = db.Column(db.String(20), default='hours')  # 'hours' or 'count'
    match_type = db.Column(db.String(20), default='suffix')  # 'suffix', 'contains', 'exact'
    priority = db.Column(db.Integer, default=10)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # キャッシュ
    _cache = None

    @classmethod
    def clear_cache(cls):
        cls._cache = None

    @classmethod
    def get_cached_rules(cls):
        """キャッシュからルールを取得"""
        if cls._cache is None:
            rules = cls.query.filter_by(is_active=True)\
                .order_by(cls.priority.desc()).all()
            cls._cache = [
                {
                    'keyword': r.keyword,
                    'unit_type': r.unit_type,
                    'match_type': r.match_type
                }
                for r in rules
            ]
        return cls._cache

    @classmethod
    def get_unit_type(cls, work_name):
        """業務名から単位タイプを判定

        Returns:
            'hours' - 時間制（1h, 2hなど）
            'count' - 件数制（1件, 2件など）
        """
        if not work_name:
            return 'hours'  # デフォルトは時間

        rules = cls.get_cached_rules()
        work_name_lower = work_name.lower()

        for rule in rules:
            keyword = rule['keyword'].lower()
            match_type = rule['match_type']

            if match_type == 'exact' and work_name_lower == keyword:
                return rule['unit_type']
            elif match_type == 'suffix' and work_name_lower.endswith(keyword):
                return rule['unit_type']
            elif match_type == 'contains' and keyword in work_name_lower:
                return rule['unit_type']

        return 'hours'  # デフォルト

    @classmethod
    def seed_default_rules(cls):
        """デフォルトルールを投入"""
        default_rules = [
            # 時間制（MTG、会議、対応系）
            {'keyword': 'MTG', 'unit_type': 'hours', 'match_type': 'contains', 'priority': 20},
            {'keyword': '会議', 'unit_type': 'hours', 'match_type': 'contains', 'priority': 20},
            {'keyword': 'ミーティング', 'unit_type': 'hours', 'match_type': 'contains', 'priority': 20},
            {'keyword': '打ち合わせ', 'unit_type': 'hours', 'match_type': 'contains', 'priority': 20},
            {'keyword': '打合せ', 'unit_type': 'hours', 'match_type': 'contains', 'priority': 20},
            {'keyword': '面談', 'unit_type': 'hours', 'match_type': 'contains', 'priority': 20},
            {'keyword': '研修', 'unit_type': 'hours', 'match_type': 'contains', 'priority': 20},
            {'keyword': '移動', 'unit_type': 'hours', 'match_type': 'contains', 'priority': 20},
            {'keyword': '対応', 'unit_type': 'hours', 'match_type': 'suffix', 'priority': 15},

            # 件数制（入力、作成、チェック系）
            {'keyword': '入力', 'unit_type': 'count', 'match_type': 'suffix', 'priority': 15},
            {'keyword': '作成', 'unit_type': 'count', 'match_type': 'suffix', 'priority': 15},
            {'keyword': 'チェック', 'unit_type': 'count', 'match_type': 'suffix', 'priority': 15},
            {'keyword': '確認', 'unit_type': 'count', 'match_type': 'suffix', 'priority': 15},
            {'keyword': '処理', 'unit_type': 'count', 'match_type': 'suffix', 'priority': 15},
            {'keyword': '登録', 'unit_type': 'count', 'match_type': 'suffix', 'priority': 15},
            {'keyword': '発注', 'unit_type': 'count', 'match_type': 'suffix', 'priority': 15},
            {'keyword': '手配', 'unit_type': 'count', 'match_type': 'suffix', 'priority': 15},
        ]

        for rule_data in default_rules:
            existing = cls.query.filter_by(keyword=rule_data['keyword']).first()
            if not existing:
                rule = cls(**rule_data)
                db.session.add(rule)

        db.session.commit()
        cls.clear_cache()

    def to_dict(self):
        return {
            'id': self.id,
            'keyword': self.keyword,
            'unit_type': self.unit_type,
            'match_type': self.match_type,
            'priority': self.priority,
            'is_active': self.is_active
        }


class SubCategoryRule(db.Model):
    """コア業務の細分化ルール"""
    __tablename__ = 'sub_category_rules'

    id = db.Column(db.Integer, primary_key=True)
    parent_category_id = db.Column(db.Integer, db.ForeignKey('display_categories.id'), nullable=True)
    sub_category_name = db.Column(db.String(50), nullable=False)  # 制作系, 専門作業系, etc.
    keyword = db.Column(db.String(100), nullable=False)
    match_type = db.Column(db.String(20), default='contains')  # 'suffix', 'contains', 'exact'
    priority = db.Column(db.Integer, default=10)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    parent_category = db.relationship('DisplayCategory', backref='sub_category_rules')

    # キャッシュ
    _cache = None

    @classmethod
    def clear_cache(cls):
        cls._cache = None

    @classmethod
    def get_cached_rules(cls):
        """キャッシュからルールを取得"""
        if cls._cache is None:
            rules = cls.query.filter_by(is_active=True)\
                .order_by(cls.priority.desc()).all()
            cls._cache = [
                {
                    'keyword': r.keyword,
                    'sub_category_name': r.sub_category_name,
                    'match_type': r.match_type,
                    'parent_category_id': r.parent_category_id
                }
                for r in rules
            ]
        return cls._cache

    @classmethod
    def get_sub_category(cls, work_name, parent_category_id=None):
        """業務名からサブカテゴリを判定

        Returns:
            サブカテゴリ名（見つからない場合はNone）
        """
        if not work_name:
            return None

        rules = cls.get_cached_rules()
        work_name_lower = work_name.lower()

        for rule in rules:
            # 親カテゴリが指定されていれば一致をチェック
            if parent_category_id and rule['parent_category_id']:
                if rule['parent_category_id'] != parent_category_id:
                    continue

            keyword = rule['keyword'].lower()
            match_type = rule['match_type']

            if match_type == 'exact' and work_name_lower == keyword:
                return rule['sub_category_name']
            elif match_type == 'suffix' and work_name_lower.endswith(keyword):
                return rule['sub_category_name']
            elif match_type == 'contains' and keyword in work_name_lower:
                return rule['sub_category_name']

        return None

    @classmethod
    def seed_default_rules(cls):
        """デフォルトルールを投入"""
        # まずコア業務カテゴリを取得
        core_category = DisplayCategory.query.filter_by(name='コア業務').first()
        core_id = core_category.id if core_category else None

        default_rules = [
            # 制作系
            {'sub_category_name': '制作系', 'keyword': 'ノート作成', 'match_type': 'contains', 'priority': 20},
            {'sub_category_name': '制作系', 'keyword': '書類作成', 'match_type': 'contains', 'priority': 20},
            {'sub_category_name': '制作系', 'keyword': '資料作成', 'match_type': 'contains', 'priority': 20},
            {'sub_category_name': '制作系', 'keyword': '作成', 'match_type': 'suffix', 'priority': 10},

            # 専門作業系
            {'sub_category_name': '専門作業系', 'keyword': 'Wチェック', 'match_type': 'contains', 'priority': 20},
            {'sub_category_name': '専門作業系', 'keyword': 'レセチェック', 'match_type': 'contains', 'priority': 20},
            {'sub_category_name': '専門作業系', 'keyword': 'チェック', 'match_type': 'suffix', 'priority': 10},

            # 顧客対応系
            {'sub_category_name': '顧客対応系', 'keyword': '電話対応', 'match_type': 'contains', 'priority': 20},
            {'sub_category_name': '顧客対応系', 'keyword': 'メール対応', 'match_type': 'contains', 'priority': 20},
            {'sub_category_name': '顧客対応系', 'keyword': 'TEL対応', 'match_type': 'contains', 'priority': 20},
            {'sub_category_name': '顧客対応系', 'keyword': '対応', 'match_type': 'suffix', 'priority': 10},

            # 技術系
            {'sub_category_name': '技術系', 'keyword': '施工', 'match_type': 'contains', 'priority': 15},
            {'sub_category_name': '技術系', 'keyword': '技工', 'match_type': 'contains', 'priority': 15},

            # 入力系
            {'sub_category_name': '入力系', 'keyword': 'ノート入力', 'match_type': 'contains', 'priority': 20},
            {'sub_category_name': '入力系', 'keyword': '入力', 'match_type': 'suffix', 'priority': 10},
        ]

        for rule_data in default_rules:
            existing = cls.query.filter_by(
                keyword=rule_data['keyword'],
                sub_category_name=rule_data['sub_category_name']
            ).first()
            if not existing:
                rule = cls(parent_category_id=core_id, **rule_data)
                db.session.add(rule)

        db.session.commit()
        cls.clear_cache()

    def to_dict(self):
        return {
            'id': self.id,
            'parent_category_id': self.parent_category_id,
            'parent_category_name': self.parent_category.name if self.parent_category else None,
            'sub_category_name': self.sub_category_name,
            'keyword': self.keyword,
            'match_type': self.match_type,
            'priority': self.priority,
            'is_active': self.is_active
        }


# ============================================
# プロジェクト・作業タイプマッピング
# ============================================

class WorkProjectMapping(db.Model):
    """業務名からAIが抽出したプロジェクト・作業タイプのマッピング"""
    __tablename__ = 'work_project_mappings'

    id = db.Column(db.Integer, primary_key=True)
    work_name = db.Column(db.String(500), unique=True, nullable=False)
    category1 = db.Column(db.String(100))  # 参考情報として保存
    category2 = db.Column(db.String(100))  # 参考情報として保存
    project = db.Column(db.String(200))  # AIが抽出したプロジェクト名
    task_type = db.Column(db.String(50))  # AIが抽出した作業タイプ
    confidence_score = db.Column(db.Float, default=0.0)
    is_confirmed = db.Column(db.Boolean, default=False)  # ユーザー確認済みフラグ
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # キャッシュ
    _cache = None

    __table_args__ = (
        db.Index('idx_project', 'project'),
        db.Index('idx_task_type', 'task_type'),
    )

    @classmethod
    def clear_cache(cls):
        cls._cache = None

    @classmethod
    def get_cached_mappings(cls):
        """全マッピングをキャッシュから取得"""
        if cls._cache is None:
            mappings = cls.query.all()
            cls._cache = {m.work_name: m for m in mappings}
        return cls._cache

    @classmethod
    def get_mapping(cls, work_name):
        """業務名からマッピングを取得"""
        mappings = cls.get_cached_mappings()
        return mappings.get(work_name)

    @classmethod
    def bulk_upsert(cls, items):
        """複数のマッピングを一括更新/追加

        items: [{work_name, category1, category2, project, task_type}, ...]
        """
        for item in items:
            existing = cls.query.filter_by(work_name=item['work_name']).first()
            if existing:
                existing.project = item.get('project', existing.project)
                existing.task_type = item.get('task_type', existing.task_type)
                existing.category1 = item.get('category1', existing.category1)
                existing.category2 = item.get('category2', existing.category2)
            else:
                mapping = cls(
                    work_name=item['work_name'],
                    category1=item.get('category1'),
                    category2=item.get('category2'),
                    project=item.get('project'),
                    task_type=item.get('task_type')
                )
                db.session.add(mapping)
        db.session.commit()
        cls.clear_cache()

    def to_dict(self):
        return {
            'id': self.id,
            'work_name': self.work_name,
            'category1': self.category1,
            'category2': self.category2,
            'project': self.project,
            'task_type': self.task_type,
            'confidence_score': self.confidence_score,
            'is_confirmed': self.is_confirmed
        }


# 標準作業タイプ一覧
STANDARD_TASK_TYPES = [
    'MTG・会議',
    '資料作成',
    'データ入力',
    'チェック・確認',
    '対応・連絡',
    '移動・訪問',
    '管理・調整',
    'その他'
]
