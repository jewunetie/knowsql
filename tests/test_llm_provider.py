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
