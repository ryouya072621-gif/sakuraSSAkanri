import sys
import os

# Windows環境でのUTF-8出力を強制（文字化け対策）
if sys.platform == 'win32':
    # 環境変数でPythonのエンコーディングをUTF-8に設定
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    # stdoutとstderrのエンコーディングを再設定
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()  # .envファイルから環境変数を読み込み

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5001)
