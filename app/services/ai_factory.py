"""
AI Provider Factory

AIプロバイダのファクトリ関数。
環境変数に基づいて適切なプロバイダを返す。
"""

import os
from typing import Optional
from .ai_base import AIProvider


_provider_instance: Optional[AIProvider] = None


def get_ai_provider() -> AIProvider:
    """
    設定されたAIプロバイダのインスタンスを取得。

    環境変数 AI_PROVIDER で切り替え可能:
    - 'anthropic' (default): Anthropic Claude API
    - 将来的に 'openai', 'gemini' 等を追加可能

    Returns:
        AIProvider: AIプロバイダインスタンス

    Raises:
        ValueError: 未知のプロバイダが指定された場合
    """
    global _provider_instance

    if _provider_instance is not None:
        return _provider_instance

    provider_name = os.environ.get('AI_PROVIDER', 'anthropic').lower()

    if provider_name == 'anthropic':
        from .anthropic_provider import AnthropicProvider
        _provider_instance = AnthropicProvider()
    else:
        raise ValueError(f"Unknown AI provider: {provider_name}")

    return _provider_instance


def reset_provider():
    """
    プロバイダインスタンスをリセット。
    主にテスト用。
    """
    global _provider_instance
    _provider_instance = None
