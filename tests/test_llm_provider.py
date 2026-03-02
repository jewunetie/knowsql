"""Tests for knowsql.llm.provider and knowsql.llm.__init__ (factory)."""

import pytest

from knowsql.llm.provider import ToolCall, LLMMessage, ToolDefinition
from knowsql.llm.errors import LLMAuthError


def test_tool_call_dataclass():
    tc = ToolCall(id="tc1", name="read_file", arguments={"path": "INDEX.md"})
    assert tc.id == "tc1"
    assert tc.name == "read_file"
    assert tc.arguments == {"path": "INDEX.md"}


def test_llm_message_defaults():
    msg = LLMMessage(role="user", content="hello")
    assert msg.tool_call_id is None
    assert msg.tool_calls is None


def test_tool_definition_dataclass():
    td = ToolDefinition(name="test", description="A test tool", parameters={"type": "object"})
    assert td.name == "test"
    assert td.description == "A test tool"
    assert td.parameters == {"type": "object"}


def test_create_provider_missing_key(monkeypatch):
    """Bug #4 regression: No API key -> LLMAuthError immediately."""
    from knowsql.llm import create_provider
    from knowsql.config import LLMConfig

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config = LLMConfig(provider="anthropic", api_key_env="ANTHROPIC_API_KEY")
    with pytest.raises(LLMAuthError, match="API key not found"):
        create_provider(config)


def test_create_provider_empty_key(monkeypatch):
    """Empty string API key -> LLMAuthError."""
    from knowsql.llm import create_provider
    from knowsql.config import LLMConfig

    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    config = LLMConfig(provider="anthropic", api_key_env="ANTHROPIC_API_KEY")
    with pytest.raises(LLMAuthError, match="API key not found"):
        create_provider(config)


def test_create_provider_unknown_provider(monkeypatch):
    from knowsql.llm import create_provider
    from knowsql.config import LLMConfig

    monkeypatch.setenv("FAKE_KEY", "sk-test")
    config = LLMConfig(provider="gemini", api_key_env="FAKE_KEY")
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        create_provider(config)


def test_create_provider_anthropic(monkeypatch):
    from knowsql.llm import create_provider
    from knowsql.llm.anthropic_provider import AnthropicProvider
    from knowsql.config import LLMConfig

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    config = LLMConfig(provider="anthropic", api_key_env="ANTHROPIC_API_KEY")
    provider = create_provider(config)
    assert isinstance(provider, AnthropicProvider)


def test_create_provider_openai(monkeypatch):
    from knowsql.llm import create_provider
    from knowsql.llm.openai_provider import OpenAIProvider
    from knowsql.config import LLMConfig

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    config = LLMConfig(provider="openai", api_key_env="OPENAI_API_KEY", model="gpt-4o")
    provider = create_provider(config)
    assert isinstance(provider, OpenAIProvider)


def test_create_provider_none_api_key_env():
    """api_key_env=None with no direct api_key -> LLMAuthError."""
    from knowsql.llm import create_provider
    from knowsql.config import LLMConfig

    config = LLMConfig(provider="anthropic", api_key_env=None)
    with pytest.raises(LLMAuthError, match="No API key provided"):
        create_provider(config)


def test_create_provider_direct_api_key(monkeypatch):
    """Direct api_key bypasses env var lookup."""
    from knowsql.llm import create_provider
    from knowsql.llm.anthropic_provider import AnthropicProvider
    from knowsql.config import LLMConfig

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config = LLMConfig(provider="anthropic", api_key="sk-direct")
    provider = create_provider(config)
    assert isinstance(provider, AnthropicProvider)


@pytest.mark.parametrize("provider_str,expected_type_name", [
    ("OPENAI", "OpenAIProvider"),
    (" Anthropic ", "AnthropicProvider"),
    ("OpenAI", "OpenAIProvider"),
])
def test_create_provider_case_insensitive(monkeypatch, provider_str, expected_type_name):
    """Provider name matching is case-insensitive and strips whitespace."""
    from knowsql.llm import create_provider
    from knowsql.config import LLMConfig

    config = LLMConfig(provider=provider_str, api_key="sk-test")
    provider = create_provider(config)
    assert type(provider).__name__ == expected_type_name


def test_create_provider_unknown_case_insensitive():
    """Unknown provider raises ValueError even with valid key."""
    from knowsql.llm import create_provider
    from knowsql.config import LLMConfig

    config = LLMConfig(provider="Gemini", api_key="sk-test")
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        create_provider(config)


def test_create_provider_malformed_config():
    """Plain object missing .provider attribute -> AttributeError."""
    from knowsql.llm import create_provider

    with pytest.raises(AttributeError):
        create_provider(object())
