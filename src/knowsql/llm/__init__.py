"""LLM provider factory."""

import os

from knowsql.config import LLMConfig
from knowsql.llm.errors import LLMAuthError
from knowsql.llm.provider import LLMProvider


def create_provider(config: LLMConfig) -> LLMProvider:
    """Create an LLM provider based on config."""
    # Resolve API key: direct key takes priority over env var
    api_key = config.api_key
    if api_key is None:
        if config.api_key_env is None:
            raise LLMAuthError(
                "API key missing. Provide api_key directly or configure api_key_env."
            )
        api_key = os.environ.get(config.api_key_env, "")

    if not api_key.strip():
        if config.api_key_env:
            raise LLMAuthError(
                f"API key missing. Set the {config.api_key_env} environment variable or provide api_key directly."
            )
        raise LLMAuthError(
            "API key missing. Provide api_key directly or configure api_key_env."
        )

    api_key = api_key.strip()

    if not config.provider or not config.provider.strip():
        raise ValueError("LLM provider must be specified.")

    # Provider imports are deferred to avoid loading heavy SDK dependencies
    # (anthropic, openai) when only one provider is needed.
    provider = config.provider.lower().strip()

    if provider == "anthropic":
        from knowsql.llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider(api_key=api_key, model=config.model)
    elif provider == "openai":
        from knowsql.llm.openai_provider import OpenAIProvider
        return OpenAIProvider(api_key=api_key, model=config.model)
    else:
        raise ValueError(f"Unknown LLM provider: {config.provider}")
