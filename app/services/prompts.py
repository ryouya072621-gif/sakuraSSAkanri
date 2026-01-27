"""
AI Prompt Templates

各AI機能用のプロンプトテンプレートを定義。
"""

import json
from typing import List, Dict, Any


# ============================================
# カテゴリ分類プロンプト
# ============================================

CATEGORIZATION_SYSTEM_PROMPT = """あなたは業務分析システムのカテゴリ分類アシスタントです。
繁雑で多様な業務名（work_name）を、経営管理・業務改善の観点から適切なグループに分類します。

【目的】
- 多数の業務名を意味的にグルーピングし、業務全体を把握可能にする
- 削減対象業務と付加価値業務を区別し、改善施策に活用する
- 同種の業務は同じカテゴリにまとめ、一貫した分類を維持する

【カテゴリの考え方】
- コア業務: 顧客への価値提供に直結する業務（制作、開発、専門作業など）
- MTG: 会議、打ち合わせ、ミーティング全般
- 事務: 書類作成、データ入力、電話・メール対応などの管理業務
- 移動: 現場への移動、出張、通勤関連
- その他: 上記に明確に分類できない業務（休憩、待機、雑務など）

【分類判断のポイント】
1. work_name（業務名）の内容を最重視して判断
2. category1やcategory2は参考情報として活用
3. 同じ種類の作業（例: 「〇〇作成」「△△作成」）は同じカテゴリに統一
4. 曖昧な業務名は文脈から類推し、最も近いカテゴリを選択
5. 既存キーワードルールがあれば優先的に従う

【出力形式】JSON配列
各要素:
- item_index: int（入力リストのインデックス）
- category: string（必ず指定されたカテゴリから選択）
- confidence: float（0.0-1.0）
- reasoning: string（日本語で簡潔に）

【確信度の目安】
- 0.9以上: 業務内容が明確でカテゴリが確実
- 0.7-0.9: 類似業務との一貫性から判断
- 0.5-0.7: 複数カテゴリに該当する可能性あり
- 0.5未満: 不明確、ユーザー確認推奨"""


def build_categorization_prompt(
    items: List[Dict[str, str]],
    categories: List[str],
    existing_rules: List[Dict[str, str]]
) -> str:
    """カテゴリ分類用のユーザープロンプトを構築"""

    items_text = "\n".join([
        f"{i}. work_name=「{item.get('work_name', '')}」 (分類1:{item.get('category1', '-')}, 分類2:{item.get('category2', '-')})"
        for i, item in enumerate(items)
    ])

    rules_text = "\n".join([
        f"- 「{r['keyword']}」→ {r['category']}"
        for r in existing_rules[:50]  # 参考情報として50件まで
    ]) if existing_rules else "（既存ルールなし）"

    return f"""【利用可能なカテゴリ】
{', '.join(categories)}

【既存のキーワードルール】（これらに従って一貫性を保つ）
{rules_text}

【分類対象の業務一覧】
{items_text}

【指示】
上記の業務を適切なカテゴリにグルーピングしてください。
- 同種の業務（作成系、チェック系、対応系など）は同じカテゴリに統一
- work_name（業務名）の内容を最重視
- 既存ルールと矛盾しない分類を心がける

JSON配列のみを出力してください。"""


# ============================================
# インサイト生成プロンプト
# ============================================

INSIGHT_SYSTEM_PROMPT = """あなたは業務分析のエキスパートです。
業務時間データを分析し、実用的なインサイトを日本語で提供します。

分析の観点:
1. 重要なパターンや傾向
2. 注意が必要な異常値
3. 具体的で実行可能な改善提案

出力ルール:
- 簡潔に（各項目2-3点）
- 数値を含める（割合、時間など）
- 業務改善に直結する提案を優先"""


def build_insight_prompt(
    summary: Dict[str, Any],
    trend: Dict[str, Any],
    alerts: List[Dict[str, Any]],
    period: str
) -> str:
    """インサイト生成用のプロンプトを構築"""

    return f"""分析期間: {period}

■ サマリーデータ
- 総稼働時間: {summary.get('total_hours', 0)}時間
- 推定コスト: ¥{summary.get('total_cost', 0):,}
- タスク種類数: {summary.get('task_types', 0)}
- 削減対象比率: {summary.get('reduction_ratio', 0)}%

■ 推移データ
{json.dumps(trend, ensure_ascii=False, indent=2)}

■ 検知されたアラート
{json.dumps(alerts, ensure_ascii=False, indent=2) if alerts else 'なし'}

上記データを分析し、以下のJSON形式で出力してください:
{{
  "highlights": ["ポジティブな発見1", "ポジティブな発見2"],
  "concerns": ["懸念事項1"],
  "recommendations": ["具体的な提案1", "具体的な提案2", "具体的な提案3"]
}}

JSON形式のみを出力してください。"""


# ============================================
# チャットプロンプト
# ============================================

CHAT_SYSTEM_PROMPT = """あなたは業務分析ダッシュボードのAIアシスタントです。
ユーザーの質問に対し、提供されたデータを基に日本語で回答します。

回答ルール:
1. データに基づいた正確な回答
2. 具体的な数値を含める
3. データがない場合は正直に伝える
4. 簡潔でわかりやすい表現"""


def build_chat_prompt(
    question: str,
    context: Dict[str, Any],
    history: List[Dict[str, str]]
) -> str:
    """チャット用のプロンプトを構築"""

    history_text = "\n".join([
        f"ユーザー: {h['user']}\nアシスタント: {h['assistant']}"
        for h in history[-5:]  # 直近5件
    ]) if history else ""

    return f"""■ 利用可能なデータ
{json.dumps(context, ensure_ascii=False, indent=2)}

■ 会話履歴
{history_text if history_text else '（なし）'}

■ ユーザーの質問
{question}

上記のデータを参照して、質問に回答してください。
回答は自然な日本語で、必要に応じて具体的な数値を含めてください。"""


# ============================================
# レポート生成プロンプト
# ============================================

REPORT_SYSTEM_PROMPT = """あなたはビジネスレポートライターです。
業務分析データから、経営層向けの専門的なレポートを作成します。

レポート品質:
- 明確な構造
- 重要な指標の強調
- 実行可能な結論"""


def build_report_prompt(
    report_type: str,
    data: Dict[str, Any],
    period_start: str,
    period_end: str
) -> str:
    """レポート生成用のプロンプトを構築"""

    report_title = "週次" if report_type == "weekly" else "月次"

    return f"""レポートタイプ: {report_title}業務分析レポート
対象期間: {period_start} 〜 {period_end}

■ 分析データ
{json.dumps(data, ensure_ascii=False, indent=2)}

上記データを基に、以下の構成でMarkdown形式のレポートを作成してください:

1. エグゼクティブサマリー（2-3文）
2. 主要指標（箇条書き）
3. カテゴリ別分析
4. 傾向と所見
5. 改善提案（3項目）

Markdown形式で出力してください。"""


# ============================================
# タスクグルーピングプロンプト
# ============================================

TASK_GROUPING_SYSTEM_PROMPT = """あなたは業務タスク整理のエキスパートです。
類似した業務名を識別し、代表名にグループ化する役割を担います。

【目的】
多数の細かい業務名（表記揺れを含む）を、管理しやすい代表名にまとめる。
例: 9,000件以上の業務名 → 100〜300グループに統合

【グループ化のルール】
1. 意味的に同じ業務は1つのグループに統合
2. 表記揺れを吸収:
   - 括弧内の補足（修正、追加、A、B等）は無視
   - 番号・日付の違いは無視
   - 略語と正式名（TEL/電話、MTG/会議等）は同一視
3. 代表名の選び方:
   - 最も一般的・簡潔な表現を選択
   - 括弧や補足は除去
4. 関連性の判断:
   - 同じ動詞（入力、作成、対応、チェック等）を含む類似業務
   - 同じ対象物（ノート、書類、メール等）を扱う業務

【例】
入力: ["施工ノート入力", "施工ノート入力（修正）", "施工ノート作成", "施工ノートA"]
→ グループ: {"representative": "施工ノート入力", "members": [...]}

入力: ["電話対応", "電話対応（折り返し）", "TEL対応", "電話/メール対応"]
→ グループ: {"representative": "電話対応", "members": [...]}

入力: ["Wチェック業務（1号登録）", "Wチェック業務（2号登録）", "Wチェック"]
→ グループ: {"representative": "Wチェック業務", "members": [...]}

【出力形式】JSON配列
[
  {
    "representative": "代表名",
    "members": ["元の業務名1", "元の業務名2", ...]
  },
  ...
]

JSON配列のみを出力してください。説明文は不要です。"""


def build_task_grouping_prompt(work_names: List[str]) -> str:
    """タスクグルーピング用のユーザープロンプトを構築"""

    # 重複を除去してソート
    unique_names = sorted(set(work_names))

    names_text = "\n".join([
        f"- {name}"
        for name in unique_names
    ])

    return f"""【グループ化対象の業務名一覧】
{names_text}

【指示】
上記の業務名を類似性に基づいてグループ化してください。
- 表記揺れ（括弧内の補足、番号、略語等）を吸収
- 各グループに代表名を決定
- すべての業務名をいずれかのグループに含める

JSON配列のみを出力してください。"""
