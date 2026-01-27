"""
AI Provider Abstract Base Classes

AIプロバイダの抽象基底クラスを定義。
将来的に他のAIプロバイダ（OpenAI, Gemini等）に切り替え可能にする。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class CategorizationResult:
    """カテゴリ分類結果"""
    category_name: str
    confidence: float  # 0.0 - 1.0
    reasoning: str


@dataclass
class InsightResult:
    """インサイト生成結果"""
    highlights: List[str]
    concerns: List[str]
    recommendations: List[str]


@dataclass
class ChatResponse:
    """チャット応答"""
    answer: str
    data_references: List[Dict[str, Any]]
    follow_up_questions: List[str]


@dataclass
class ReportResult:
    """レポート生成結果"""
    content: str
    format: str  # 'markdown' or 'html'


@dataclass
class TaskGroup:
    """タスクグループ"""
    representative: str  # 代表名
    members: List[str]   # グループに含まれる元の業務名


@dataclass
class TaskGroupingResult:
    """タスクグルーピング結果"""
    groups: List[TaskGroup]
    original_count: int
    grouped_count: int


class AIProviderError(Exception):
    """AI Provider base exception"""
    pass


class AIRateLimitError(AIProviderError):
    """Rate limit exceeded"""
    pass


class AIAuthenticationError(AIProviderError):
    """Invalid API key"""
    pass


class AIProvider(ABC):
    """
    Abstract base class for AI providers.

    すべてのAIプロバイダはこのクラスを継承し、
    各メソッドを実装する必要がある。
    """

    @abstractmethod
    def categorize_work_items(
        self,
        items: List[Dict[str, str]],
        categories: List[str],
        existing_rules: List[Dict[str, str]]
    ) -> List[CategorizationResult]:
        """
        業務アイテムをカテゴリ分類する。

        Args:
            items: 分類対象の業務リスト
                   [{'category1': str, 'category2': str, 'work_name': str}, ...]
            categories: 利用可能なカテゴリ名リスト
            existing_rules: 既存のキーワードルール
                           [{'keyword': str, 'category': str}, ...]

        Returns:
            List[CategorizationResult]: 各アイテムの分類結果
        """
        pass

    @abstractmethod
    def generate_insights(
        self,
        summary_data: Dict[str, Any],
        trend_data: Dict[str, Any],
        alerts_data: List[Dict[str, Any]],
        period: str
    ) -> InsightResult:
        """
        業務データからインサイトを生成する。

        Args:
            summary_data: KPIサマリー（総時間、コスト、削減率等）
            trend_data: 推移データ
            alerts_data: 異常値アラート
            period: 分析期間の説明文

        Returns:
            InsightResult: 生成されたインサイト
        """
        pass

    @abstractmethod
    def chat_query(
        self,
        question: str,
        context_data: Dict[str, Any],
        conversation_history: List[Dict[str, str]]
    ) -> ChatResponse:
        """
        自然言語の質問に回答する。

        Args:
            question: ユーザーの質問
            context_data: 現在のダッシュボードデータ
            conversation_history: 会話履歴
                                 [{'user': str, 'assistant': str}, ...]

        Returns:
            ChatResponse: AIの回答
        """
        pass

    @abstractmethod
    def generate_report(
        self,
        report_type: str,
        data: Dict[str, Any],
        period_start: str,
        period_end: str
    ) -> ReportResult:
        """
        レポートを生成する。

        Args:
            report_type: 'weekly' or 'monthly'
            data: レポート用の集計データ
            period_start: 期間開始日 (YYYY-MM-DD)
            period_end: 期間終了日 (YYYY-MM-DD)

        Returns:
            ReportResult: 生成されたレポート
        """
        pass

    @abstractmethod
    def group_similar_tasks(
        self,
        work_names: List[str]
    ) -> TaskGroupingResult:
        """
        類似タスクをグループ化する。

        表記揺れ（括弧内の補足、番号、略語等）を吸収し、
        意味的に同じ業務を1つのグループにまとめる。

        Args:
            work_names: 業務名のリスト

        Returns:
            TaskGroupingResult: グループ化結果
        """
        pass
