import os

basedir = os.path.abspath(os.path.dirname(__file__))

def get_cloud_sql_engine_options():
    """Cloud SQL用のエンジンオプションを取得"""
    cloud_sql_instance = os.environ.get('CLOUD_SQL_CONNECTION_NAME')
    if not cloud_sql_instance:
        return {}

    try:
        from google.cloud.sql.connector import Connector

        connector = Connector()

        def getconn():
            return connector.connect(
                cloud_sql_instance,
                "pg8000",
                user=os.environ.get('DB_USER', 'postgres'),
                password=os.environ.get('DB_PASSWORD', ''),
                db=os.environ.get('DB_NAME', 'ssa'),
            )

        return {
            'creator': getconn,
            'pool_size': 5,
            'pool_timeout': 30,
            'pool_recycle': 1800,
            'max_overflow': 10,
        }
    except ImportError:
        return {}

def get_database_url():
    """データベースURLを取得（Cloud SQL対応）"""
    # 環境変数で明示的に指定されている場合はそれを使用
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        return db_url

    # Cloud SQL設定がある場合はPostgreSQLを使用
    cloud_sql_instance = os.environ.get('CLOUD_SQL_CONNECTION_NAME')
    if cloud_sql_instance:
        # Cloud SQL Python Connectorを使用するため、ダミーURL
        return "postgresql+pg8000://"

    # デフォルトはローカルSQLite
    return 'sqlite:///' + os.path.join(basedir, 'instance', 'app.db')

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Cloud SQL または通常のDB用エンジンオプション
    _cloud_sql_options = get_cloud_sql_engine_options()
    if _cloud_sql_options:
        SQLALCHEMY_ENGINE_OPTIONS = _cloud_sql_options
    elif not get_database_url().startswith('sqlite'):
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_size': 5,
            'pool_timeout': 30,
            'pool_recycle': 1800,
            'max_overflow': 10,
        }
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {}
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
