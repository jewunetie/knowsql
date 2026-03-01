"""Tests for knowsql.llm.openai_provider."""

import json
from types import SimpleNamespace

import pytest

from knowsql.llm.openai_provider import OpenAIProvider
from knowsql.llm.provider import LLMMessage, ToolCall, ToolDefinition
from knowsql.llm.errors import LLMError


@pytest.fixture
def provider():
    return OpenAIProvider(api_key="sk-test-dummy", model="gpt-test")


class TestPrepareMessages:
    def test_system(self, provider):
        msgs = [LLMMessage(role="system", content="Be helpful")]
        result = provider._prepare_messages(msgs)
        assert result[0] == {"role": "system", "content": "Be helpful"}

    def test_tool_result(self, provider):
        msgs = [LLMMessage(role="tool", content="result data", tool_call_id="tc_1")]
        result = provider._prepare_messages(msgs)
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "tc_1"
        assert result[0]["content"] == "result data"

    def test_assistant_with_tools(self, provider):
        msgs = [
            LLMMessage(
                role="assistant",
                content="",
                tool_calls=[ToolCall(id="tc_1", name="fn", arguments={"x": 1})],
            ),
        ]
        result = provider._prepare_messages(msgs)
        assert result[0]["role"] == "assistant"
        tc = result[0]["tool_calls"][0]
        assert tc["id"] == "tc_1"
        assert tc["type"] == "function"
        assert json.loads(tc["function"]["arguments"]) == {"x": 1}


class TestConvertTool:
    def test_convert_tool(self, provider):
        tool = ToolDefinition(
            name="read_file",
            description="Read a file",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}},
        )
        result = provider._convert_tool(tool)
        assert result["type"] == "function"
        assert result["function"]["name"] == "read_file"
        assert result["function"]["parameters"] == tool.parameters


class TestParseResponse:
    def _make_response(self, content="Hello", tool_calls=None):
        msg = SimpleNamespace(content=content, tool_calls=tool_calls)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    def test_text(self, provider):
        resp = self._make_response(content="Hello world")
        msg = provider._parse_response(resp)
        assert msg.role == "assistant"
        assert msg.content == "Hello world"
        assert msg.tool_calls is None

    def test_tool_calls(self, provider):
        tc = SimpleNamespace(
            id="tc_1",
            function=SimpleNamespace(name="read_file", arguments='{"path": "INDEX.md"}'),
        )
        resp = self._make_response(content=None, tool_calls=[tc])
        msg = provider._parse_response(resp)
        assert msg.tool_calls is not None
        assert msg.tool_calls[0].name == "read_file"
        assert msg.tool_calls[0].arguments == {"path": "INDEX.md"}

    def test_no_tool_calls(self, provider):
        resp = self._make_response(content="Just text", tool_calls=None)
        msg = provider._parse_response(resp)
        assert msg.tool_calls is None


class TestCompleteJson:
    def test_valid(self, provider, monkeypatch):
        mock_resp = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"result": 42}'))]
        )
        monkeypatch.setattr(
            provider.client.chat.completions, "create", lambda **kwargs: mock_resp
        )
        result = provider.complete_json([LLMMessage(role="user", content="Return JSON")])
        assert result == {"result": 42}

    def test_invalid(self, provider, monkeypatch):
        """Bug #3 regression: Invalid JSON -> LLMError."""
        mock_resp = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="not valid json {{{"))]
        )
        monkeypatch.setattr(
            provider.client.chat.completions, "create", lambda **kwargs: mock_resp
        )
        with pytest.raises(LLMError, match="Failed to parse JSON"):
            provider.complete_json([LLMMessage(role="user", content="Return JSON")])

    def test_empty_response(self, provider, monkeypatch):
        mock_resp = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=None))]
        )
        monkeypatch.setattr(
            provider.client.chat.completions, "create", lambda **kwargs: mock_resp
        )
        # None content defaults to "{}" which parses to empty dict
        result = provider.complete_json([LLMMessage(role="user", content="Return JSON")])
        assert result == {}
