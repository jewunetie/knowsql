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


@pytest.mark.live_llm
class TestCompleteTextLive:
    """Tests that run against mock or real OpenAI API."""

    @pytest.fixture
    def active_provider(self, provider, openai_live_provider, llm_backend, monkeypatch):
        if llm_backend == "openai":
            return openai_live_provider
        mock_resp = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(
                content="Hello", tool_calls=None
            ))]
        )
        monkeypatch.setattr(provider.client.chat.completions, "create", lambda **kw: mock_resp)
        return provider

    def test_text_response(self, active_provider):
        result = active_provider.complete(
            [LLMMessage(role="user", content="Reply with one word: hello")],
        )
        assert isinstance(result, LLMMessage)
        assert result.role == "assistant"
        assert len(result.content) > 0

    def test_system_message(self, active_provider):
        result = active_provider.complete([
            LLMMessage(role="system", content="You are a calculator. Only output numbers."),
            LLMMessage(role="user", content="What is 2+2?"),
        ])
        assert isinstance(result, LLMMessage)
        assert result.role == "assistant"
        assert len(result.content) > 0


@pytest.mark.live_llm
class TestCompleteJsonLive:
    @pytest.fixture
    def active_provider(self, provider, openai_live_provider, llm_backend, monkeypatch):
        if llm_backend == "openai":
            return openai_live_provider
        mock_resp = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(
                content='{"name": "test", "count": 5}'
            ))]
        )
        monkeypatch.setattr(provider.client.chat.completions, "create", lambda **kw: mock_resp)
        return provider

    def test_json_response(self, active_provider):
        result = active_provider.complete_json([
            LLMMessage(role="user", content='Return JSON with keys "name" (string) and "count" (integer).'),
        ])
        assert isinstance(result, dict)
        assert "name" in result
        assert "count" in result


@pytest.mark.live_llm
class TestToolCallingLive:
    WEATHER_TOOL = ToolDefinition(
        name="get_weather",
        description="Get the current weather for a city.",
        parameters={
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City name"}},
            "required": ["city"],
        },
    )

    @pytest.fixture
    def active_provider(self, provider, openai_live_provider, llm_backend, monkeypatch):
        if llm_backend == "openai":
            return openai_live_provider
        tc = SimpleNamespace(
            id="tc_mock", function=SimpleNamespace(name="get_weather", arguments='{"city": "Paris"}')
        )
        mock_resp = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[tc]))]
        )
        monkeypatch.setattr(provider.client.chat.completions, "create", lambda **kw: mock_resp)
        return provider

    def test_tool_call(self, active_provider):
        result = active_provider.complete(
            [LLMMessage(role="user", content="What is the weather in Paris?")],
            tools=[self.WEATHER_TOOL],
        )
        assert isinstance(result, LLMMessage)
        assert result.tool_calls is not None
        assert len(result.tool_calls) >= 1
        tc = result.tool_calls[0]
        assert isinstance(tc, ToolCall)
        assert tc.name == "get_weather"
        assert isinstance(tc.arguments, dict)
        assert "city" in tc.arguments

    def test_tool_round_trip(self, active_provider, llm_backend, monkeypatch, provider):
        # Step 1: get tool call
        result1 = active_provider.complete(
            [LLMMessage(role="user", content="What is the weather in Paris?")],
            tools=[self.WEATHER_TOOL],
        )
        assert result1.tool_calls is not None
        tc = result1.tool_calls[0]

        # Step 2: provide tool result, get final answer
        if llm_backend != "openai":
            mock_resp2 = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(
                    content="The weather in Paris is sunny.", tool_calls=None
                ))]
            )
            monkeypatch.setattr(provider.client.chat.completions, "create", lambda **kw: mock_resp2)
            active = provider
        else:
            active = active_provider

        messages = [
            LLMMessage(role="user", content="What is the weather in Paris?"),
            result1,
            LLMMessage(role="tool", content='{"weather": "sunny", "temp": 22}', tool_call_id=tc.id),
        ]
        result2 = active.complete(messages, tools=[self.WEATHER_TOOL])
        assert isinstance(result2, LLMMessage)
        assert result2.role == "assistant"
        assert len(result2.content) > 0
