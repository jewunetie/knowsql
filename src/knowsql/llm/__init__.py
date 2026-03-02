"""LLM provider factory."""

import os

from knowsql.config import LLMConfig
from knowsql.llm.errors import LLMAuthError
from knowsql.llm.provider import LLMProvider


def create_provider(config: LLMConfig) -> LLMProvider:
    """Create an LLM provider based on config."""
    # Resolve API key: direct key takes priority over env var
    api_key = config.api_key
    if not api_key:
        if config.api_key_env is None:
            raise LLMAuthError(
                "No API key provided and no api_key_env configured."
            )
        api_key = os.environ.get(config.api_key_env, "")

    if not api_key:
        raise LLMAuthError(
            f"API key not found. Set the {config.api_key_env} environment variable."
        )

    provider = config.provider.lower().strip()

    if provider == "anthropic":
        from knowsql.llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider(api_key=api_key, model=config.model)
    elif provider == "openai":
        from knowsql.llm.openai_provider import OpenAIProvider
        return OpenAIProvider(api_key=api_key, model=config.model)
    else:
        raise ValueError(f"Unknown LLM provider: {config.provider}")
