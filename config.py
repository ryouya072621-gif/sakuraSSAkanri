import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_timeout': 60,
        'pool_recycle': 1800,
        'max_overflow': 20,
    }
    UPLOAD_FOLDER = os.path.join(basedir, 'instance', 'uploads')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max upload

    # 分析ロジック閾値
    ALERT_MIN_HOURS = 5              # アラート発火の最低時間（h）
    ALERT_CHANGE_THRESHOLD = 50      # 週次変動アラート閾値（%）
    REDUCTION_RATIO_WARNING = 15     # 削減比率警告閾値（%）
    STAR_EXCELLENT_THRESHOLD = 80    # ★★★絶対評価閾値（効率スコア）
    STAR_GOOD_THRESHOLD = 50         # ★★絶対評価閾値（効率スコア）

    # AI設定（Anthropic Claude API）
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
    ANTHROPIC_MODEL = os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')
    AI_PROVIDER = os.environ.get('AI_PROVIDER', 'anthropic')
    AI_MAX_BATCH_SIZE = 500          # カテゴリ分類の最大バッチサイズ
    AI_INSIGHT_CACHE_HOURS = 720     # インサイトキャッシュ時間（30日間）
