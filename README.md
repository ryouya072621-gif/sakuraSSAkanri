# 個人業務分析レポートシステム

Excelファイルから業務データを読み込み、カテゴリ別・日次の業務分析レポートを生成するWebアプリケーションです。

## 主な機能

- 📊 Excelファイルからの業務データアップロード
- 📈 業務カテゴリ別の時間消費分析
- 📅 日次・期間別のレポート生成
- 💰 推定コスト計算
- 🎯 業務別時間消費ランキング
- ⚙️ カテゴリ・キーワード管理

## 技術スタック

- **Backend:** Flask 3.0.0
- **Database:** SQLAlchemy (SQLite)
- **Excel処理:** openpyxl 3.1.2
- **Frontend:** HTML, CSS, JavaScript

## セットアップ

### 前提条件

- Python 3.8以上
- pip

### インストール手順

1. リポジトリのクローン

```bash
git clone https://github.com/USERNAME/personal-work-analysis.git
cd personal-work-analysis
```

2. 仮想環境の作成と有効化

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

3. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

4. 環境変数の設定

`.env.example`を`.env`にコピーして、必要な値を設定します。

```bash
# Windows
copy .env.example .env

# macOS/Linux
cp .env.example .env
```

`.env`ファイルを編集:
```
SECRET_KEY=ランダムな文字列に変更してください
```

5. データベースの初期化

アプリケーションを初回起動すると、自動的にデータベースが作成されます。

6. アプリケーションの起動

```bash
python run.py
```

ブラウザで http://localhost:5000 にアクセスします。

## 使い方

### 業務データのアップロード

1. トップページの「データをアップロード」ボタンをクリック
2. Excelファイル（.xlsx）を選択
3. アップロード完了後、自動的にダッシュボードにリダイレクト

### レポートの閲覧

- ダッシュボードで期間を指定してレポートを表示
- 業務カテゴリ別の構成比を円グラフで確認
- 日次業務内訳の推移を棒グラフで確認
- 業務別時間消費ランキングを確認

### 管理機能

- 設定メニューから業務カテゴリの追加・編集
- キーワードマッピングの設定
- 推定時給の設定

## プロジェクト構成

```
personal-work-analysis/
├── app/
│   ├── __init__.py          # Flaskアプリ初期化
│   ├── models.py            # データモデル定義
│   ├── routes/              # ルーティング
│   │   ├── admin.py         # 管理機能
│   │   ├── api.py           # APIエンドポイント
│   │   ├── main.py          # メインルート
│   │   └── upload.py        # ファイルアップロード
│   ├── static/              # 静的ファイル
│   │   ├── css/             # スタイルシート
│   │   └── js/              # JavaScript
│   └── templates/           # HTMLテンプレート
│       ├── admin/           # 管理画面
│       ├── base.html        # ベーステンプレート
│       ├── dashboard.html   # ダッシュボード
│       └── upload.html      # アップロード画面
├── instance/                # データベース・アップロードファイル（.gitignore）
├── config.py                # 設定ファイル
├── requirements.txt         # 依存パッケージ
├── run.py                   # アプリ起動スクリプト
└── fix_keywords.py          # キーワード修正ユーティリティ
```

## データベーススキーマ

### TaskRecord（業務記録）
- 日付、開始時刻、終了時刻
- タスク名、カテゴリ
- 消費時間（分）

### Category（カテゴリ）
- カテゴリ名、色

### Keyword（キーワードマッピング）
- キーワード、カテゴリ（自動分類用）

### Settings（設定）
- 推定時給など

## ライセンス

このプロジェクトは個人使用のために作成されました。

## 貢献

プルリクエストを歓迎します。大きな変更の場合は、まずissueを開いて変更内容を議論してください。
