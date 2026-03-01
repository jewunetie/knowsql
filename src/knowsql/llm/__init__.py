"""LLM provider factory."""

import os

from knowsql.llm.provider import LLMProvider


def create_provider(config) -> LLMProvider:
    """Create an LLM provider based on config."""
    from knowsql.llm.errors import LLMAuthError

    api_key = os.environ.get(config.api_key_env, "")
    if not api_key:
        raise LLMAuthError(
            f"API key not found. Set the {config.api_key_env} environment variable."
        )

    if config.provider == "anthropic":
        from knowsql.llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider(api_key=api_key, model=config.model)
    elif config.provider == "openai":
        from knowsql.llm.openai_provider import OpenAIProvider
        return OpenAIProvider(api_key=api_key, model=config.model)
    else:
        raise ValueError(f"Unknown LLM provider: {config.provider}")
