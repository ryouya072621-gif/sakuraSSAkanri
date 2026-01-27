"""
Anthropic Claude API Provider

Anthropic Claude APIを使用したAIプロバイダ実装。
"""

import os
import json
import logging
from typing import List, Dict, Any

from .ai_base import (
    AIProvider,
    CategorizationResult,
    InsightResult,
    ChatResponse,
    ReportResult,
    TaskGroup,
    TaskGroupingResult,
    AIProviderError,
    AIRateLimitError,
    AIAuthenticationError
)
from .prompts import (
    CATEGORIZATION_SYSTEM_PROMPT,
    INSIGHT_SYSTEM_PROMPT,
    CHAT_SYSTEM_PROMPT,
    REPORT_SYSTEM_PROMPT,
    TASK_GROUPING_SYSTEM_PROMPT,
    build_categorization_prompt,
    build_insight_prompt,
    build_chat_prompt,
    build_report_prompt,
    build_task_grouping_prompt
)

logger = logging.getLogger(__name__)


class AnthropicProvider(AIProvider):
    """Anthropic Claude API implementation"""

    def __init__(self):
        self.api_key = os.environ.get('ANTHROPIC_API_KEY')
        self.model = os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')
        self.max_tokens = 8192  # 4096から増加（レスポンス切り捨て対策）

        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not set. AI features will be unavailable.")

    def _make_request(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = None
    ) -> str:
        """Make API request and return response text"""
        if not self.api_key:
            raise AIAuthenticationError("ANTHROPIC_API_KEY is not configured")

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)

            response = client.messages.create(
                model=self.model,
                max_tokens=max_tokens or self.max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )

            logger.info(
                f"AI request completed: input={response.usage.input_tokens}, "
                f"output={response.usage.output_tokens}"
            )

            return response.content[0].text

        except anthropic.RateLimitError as e:
            logger.error(f"Rate limit exceeded: {e}")
            raise AIRateLimitError("API rate limit exceeded. Please try again later.")

        except anthropic.AuthenticationError as e:
            logger.error(f"Authentication failed: {e}")
            raise AIAuthenticationError("Invalid API key.")

        except Exception as e:
            logger.error(f"AI request failed: {e}")
            raise AIProviderError(f"AI service error: {str(e)}")

    def _parse_json_response(self, text: str) -> Any:
        """Extract and parse JSON from response text"""
        text = text.strip()

        # コードブロックマーカーを除去（改行を考慮）
        if text.startswith("```json"):
            text = text[7:]  # "```json" を除去
            if text.startswith("\n"):
                text = text[1:]  # 続く改行を除去
        elif text.startswith("```"):
            text = text[3:]
            if text.startswith("\n"):
                text = text[1:]

        # 末尾の ``` を除去
        if text.endswith("```"):
            text = text[:-3]
        elif "```" in text:
            # 途中で切れている場合、最後の ``` より前を使用
            text = text.split("```")[0]

        text = text.strip()

        # 配列が途中で切れている場合の処理
        if text.startswith("[") and not text.endswith("]"):
            # 最後の完全なオブジェクトを見つける
            last_complete = text.rfind("}")
            if last_complete > 0:
                text = text[:last_complete + 1] + "]"
                logger.warning("JSON array was truncated, attempting recovery")

        # オブジェクトが途中で切れている場合の処理
        if text.startswith("{") and not text.endswith("}"):
            # 最後の完全なキー-値ペアを見つける
            last_quote = text.rfind('"')
            if last_quote > 0:
                # 不完全なオブジェクトは空のオブジェクトとして処理
                text = "{}"
                logger.warning("JSON object was truncated, returning empty object")

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}\nText: {text[:500]}")
            raise AIProviderError(f"Failed to parse AI response as JSON")

    def categorize_work_items(
        self,
        items: List[Dict[str, str]],
        categories: List[str],
        existing_rules: List[Dict[str, str]]
    ) -> List[CategorizationResult]:
        """業務アイテムをカテゴリ分類"""

        if not items:
            return []

        user_prompt = build_categorization_prompt(items, categories, existing_rules)
        response_text = self._make_request(CATEGORIZATION_SYSTEM_PROMPT, user_prompt)

        parsed = self._parse_json_response(response_text)

        results = []
        for item in parsed:
            results.append(CategorizationResult(
                category_name=item.get('category', categories[0] if categories else 'その他'),
                confidence=float(item.get('confidence', 0.5)),
                reasoning=item.get('reasoning', '')
            ))

        return results

    def generate_insights(
        self,
        summary_data: Dict[str, Any],
        trend_data: Dict[str, Any],
        alerts_data: List[Dict[str, Any]],
        period: str
    ) -> InsightResult:
        """インサイトを生成"""

        user_prompt = build_insight_prompt(summary_data, trend_data, alerts_data, period)
        response_text = self._make_request(INSIGHT_SYSTEM_PROMPT, user_prompt)

        parsed = self._parse_json_response(response_text)

        return InsightResult(
            highlights=parsed.get('highlights', []),
            concerns=parsed.get('concerns', []),
            recommendations=parsed.get('recommendations', [])
        )

    def chat_query(
        self,
        question: str,
        context_data: Dict[str, Any],
        conversation_history: List[Dict[str, str]]
    ) -> ChatResponse:
        """チャット質問に回答"""

        user_prompt = build_chat_prompt(question, context_data, conversation_history)
        response_text = self._make_request(CHAT_SYSTEM_PROMPT, user_prompt)

        # チャットの場合はプレーンテキストで返す
        return ChatResponse(
            answer=response_text.strip(),
            data_references=[],
            follow_up_questions=[]
        )

    def generate_report(
        self,
        report_type: str,
        data: Dict[str, Any],
        period_start: str,
        period_end: str
    ) -> ReportResult:
        """レポートを生成"""

        user_prompt = build_report_prompt(report_type, data, period_start, period_end)
        response_text = self._make_request(
            REPORT_SYSTEM_PROMPT,
            user_prompt,
            max_tokens=8192  # レポートは長くなる可能性
        )

        return ReportResult(
            content=response_text.strip(),
            format='markdown'
        )

    def group_similar_tasks(
        self,
        work_names: List[str]
    ) -> TaskGroupingResult:
        """類似タスクをグループ化"""

        if not work_names:
            return TaskGroupingResult(groups=[], original_count=0, grouped_count=0)

        # 重複を除去したユニーク数を記録
        unique_names = list(set(work_names))
        original_count = len(unique_names)

        user_prompt = build_task_grouping_prompt(unique_names)
        response_text = self._make_request(
            TASK_GROUPING_SYSTEM_PROMPT,
            user_prompt,
            max_tokens=8192  # 多数のグループを返す可能性
        )

        parsed = self._parse_json_response(response_text)

        groups = []
        for item in parsed:
            groups.append(TaskGroup(
                representative=item.get('representative', ''),
                members=item.get('members', [])
            ))

        return TaskGroupingResult(
            groups=groups,
            original_count=original_count,
            grouped_count=len(groups)
        )
