"""Tests for knowsql.llm.anthropic_provider (unit tests on internal methods, no real API calls)."""

from types import SimpleNamespace

import pytest

from knowsql.llm.anthropic_provider import AnthropicProvider
from knowsql.llm.provider import LLMMessage, ToolCall, ToolDefinition
from knowsql.llm.errors import LLMAuthError, LLMRateLimitError, LLMContextError, LLMError


@pytest.fixture
def provider(monkeypatch):
    """Create an AnthropicProvider with a dummy key, mocking the anthropic import."""
    # We need the real import to succeed for the class to work
    return AnthropicProvider(api_key="sk-test-dummy", model="claude-test")


class TestPrepareMessages:
    def test_extracts_system(self, provider):
        msgs = [
            LLMMessage(role="system", content="You are helpful."),
            LLMMessage(role="user", content="Hi"),
        ]
        api_msgs, system = provider._prepare_messages(msgs)
        assert system == "You are helpful."
        assert len(api_msgs) == 1
        assert api_msgs[0]["role"] == "user"

    def test_tool_result(self, provider):
        msgs = [
            LLMMessage(role="tool", content="file content here", tool_call_id="tc_123"),
        ]
        api_msgs, _ = provider._prepare_messages(msgs)
        assert api_msgs[0]["role"] == "user"
        assert api_msgs[0]["content"][0]["type"] == "tool_result"
        assert api_msgs[0]["content"][0]["tool_use_id"] == "tc_123"

    def test_assistant_with_tool_calls(self, provider):
        msgs = [
            LLMMessage(
                role="assistant",
                content="Let me read that.",
                tool_calls=[ToolCall(id="tc_1", name="read_file", arguments={"path": "INDEX.md"})],
            ),
        ]
        api_msgs, _ = provider._prepare_messages(msgs)
        content = api_msgs[0]["content"]
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "Let me read that."
        assert content[1]["type"] == "tool_use"
        assert content[1]["name"] == "read_file"

    def test_plain_messages(self, provider):
        msgs = [
            LLMMessage(role="user", content="Hello"),
            LLMMessage(role="assistant", content="Hi!"),
        ]
        api_msgs, system = provider._prepare_messages(msgs)
        assert system is None
        assert len(api_msgs) == 2
        assert api_msgs[0] == {"role": "user", "content": "Hello"}
        assert api_msgs[1] == {"role": "assistant", "content": "Hi!"}


class TestMergeConsecutiveRoles:
    def test_merge_consecutive_same_role(self, provider):
        msgs = [
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": "World"},
        ]
        merged = provider._merge_consecutive_roles(msgs)
        assert len(merged) == 1
        # Content should be normalized to list of blocks
        assert isinstance(merged[0]["content"], list)
        assert merged[0]["content"][0]["text"] == "Hello"
        assert merged[0]["content"][1]["text"] == "World"

    def test_preserves_content_blocks(self, provider):
        msgs = [
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "1", "content": "result"}]},
            {"role": "user", "content": "follow up"},
        ]
        merged = provider._merge_consecutive_roles(msgs)
        assert len(merged) == 1
        assert len(merged[0]["content"]) == 2

    def test_no_mutation(self, provider):
        """Bug #8 regression: Original messages list not mutated."""
        original_msgs = [
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": "World"},
        ]
        # Keep copies for comparison
        original_copy = [dict(m) for m in original_msgs]
        provider._merge_consecutive_roles(original_msgs)
        # Original should be unchanged
        assert original_msgs[0]["content"] == original_copy[0]["content"]
        assert original_msgs[1]["content"] == original_copy[1]["content"]

    def test_empty_list(self, provider):
        assert provider._merge_consecutive_roles([]) == []

    def test_single_message(self, provider):
        msgs = [{"role": "user", "content": "Only one"}]
        result = provider._merge_consecutive_roles(msgs)
        assert len(result) == 1


class TestConvertTool:
    def test_convert_tool(self, provider):
        tool = ToolDefinition(
            name="read_file",
            description="Read a file",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}},
        )
        result = provider._convert_tool(tool)
        assert result["name"] == "read_file"
        assert result["description"] == "Read a file"
        assert result["input_schema"] == tool.parameters


class TestParseResponse:
    def _make_response(self, blocks):
        """Helper to create a mock Anthropic response."""
        return SimpleNamespace(content=[SimpleNamespace(**b) for b in blocks])

    def test_text_only(self, provider):
        resp = self._make_response([{"type": "text", "text": "Hello world"}])
        msg = provider._parse_response(resp)
        assert msg.role == "assistant"
        assert msg.content == "Hello world"
        assert msg.tool_calls is None

    def test_tool_use(self, provider):
        resp = self._make_response([{
            "type": "tool_use",
            "id": "tc_1",
            "name": "read_file",
            "input": {"path": "INDEX.md"},
        }])
        msg = provider._parse_response(resp)
        assert msg.tool_calls is not None
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].name == "read_file"

    def test_mixed(self, provider):
        resp = self._make_response([
            {"type": "text", "text": "Let me read that."},
            {"type": "tool_use", "id": "tc_1", "name": "read_file", "input": {"path": "INDEX.md"}},
        ])
        msg = provider._parse_response(resp)
        assert msg.content == "Let me read that."
        assert msg.tool_calls is not None

    def test_multiple_text_blocks(self, provider):
        resp = self._make_response([
            {"type": "text", "text": "Part 1"},
            {"type": "text", "text": "Part 2"},
        ])
        msg = provider._parse_response(resp)
        assert msg.content == "Part 1\nPart 2"


class TestExtractText:
    def test_extract_text(self, provider):
        resp = SimpleNamespace(content=[
            SimpleNamespace(type="text", text="Hello"),
            SimpleNamespace(type="tool_use", id="tc1", name="x", input={}),
        ])
        assert provider._extract_text(resp) == "Hello"

    def test_extract_text_no_text(self, provider):
        resp = SimpleNamespace(content=[
            SimpleNamespace(type="tool_use", id="tc1", name="x", input={}),
        ])
        assert provider._extract_text(resp) == ""


class TestCompleteJson:
    def test_double_brace(self, provider, monkeypatch):
        """Bug #2 regression: LLM returns `{...}` with prefill `{` -> valid JSON."""
        # The LLM returned the opening brace itself: `{"key": "value"}`
        # With prefill `{`, the code does `"{" + raw`, resulting in `{{"key": "value"}`
        # The fallback should handle this by trying `raw` directly.
        mock_response = SimpleNamespace(content=[
            SimpleNamespace(type="text", text='{"key": "value"}')
        ])
        monkeypatch.setattr(provider.client.messages, "create", lambda **kwargs: mock_response)
        result = provider.complete_json([LLMMessage(role="user", content="Return JSON")])
        assert result == {"key": "value"}

    def test_normal(self, provider, monkeypatch):
        """LLM returns `"key": "value"}` with prefill `{` -> `{"key": "value"}`."""
        mock_response = SimpleNamespace(content=[
            SimpleNamespace(type="text", text='"key": "value"}')
        ])
        monkeypatch.setattr(provider.client.messages, "create", lambda **kwargs: mock_response)
        result = provider.complete_json([LLMMessage(role="user", content="Return JSON")])
        assert result == {"key": "value"}


@pytest.mark.live_llm
class TestCompleteTextLive:
    @pytest.fixture
    def active_provider(self, provider, anthropic_live_provider, llm_backend, monkeypatch):
        if llm_backend == "anthropic":
            return anthropic_live_provider
        mock_resp = SimpleNamespace(content=[SimpleNamespace(type="text", text="Hello")])
        monkeypatch.setattr(provider.client.messages, "create", lambda **kw: mock_resp)
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
    def active_provider(self, provider, anthropic_live_provider, llm_backend, monkeypatch):
        if llm_backend == "anthropic":
            return anthropic_live_provider
        mock_resp = SimpleNamespace(content=[
            SimpleNamespace(type="text", text='"name": "test", "count": 5}')
        ])
        monkeypatch.setattr(provider.client.messages, "create", lambda **kw: mock_resp)
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
    def active_provider(self, provider, anthropic_live_provider, llm_backend, monkeypatch):
        if llm_backend == "anthropic":
            return anthropic_live_provider
        mock_resp = SimpleNamespace(content=[
            SimpleNamespace(type="tool_use", id="tc_mock", name="get_weather", input={"city": "Paris"})
        ])
        monkeypatch.setattr(provider.client.messages, "create", lambda **kw: mock_resp)
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


class TestExceptionMapping:
    """Test that SDK exceptions are mapped to the correct LLMError subtypes."""

    @pytest.fixture
    def mock_response(self):
        """Minimal httpx.Response mock for SDK exception constructors."""
        import httpx
        return httpx.Response(status_code=400, request=httpx.Request("POST", "https://api.anthropic.com"))

    def _raise_on_create(self, provider, monkeypatch, exc):
        def raiser(**kwargs):
            raise exc
        monkeypatch.setattr(provider.client.messages, "create", raiser)

    def test_auth_error_complete(self, provider, monkeypatch, mock_response):
        import anthropic
        self._raise_on_create(provider, monkeypatch,
            anthropic.AuthenticationError("invalid api key", response=mock_response, body=None))
        with pytest.raises(LLMAuthError, match="authentication failed"):
            provider.complete([LLMMessage(role="user", content="hi")])

    def test_auth_error_complete_json(self, provider, monkeypatch, mock_response):
        import anthropic
        self._raise_on_create(provider, monkeypatch,
            anthropic.AuthenticationError("invalid api key", response=mock_response, body=None))
        with pytest.raises(LLMAuthError, match="authentication failed"):
            provider.complete_json([LLMMessage(role="user", content="hi")])

    def test_rate_limit_complete(self, provider, monkeypatch, mock_response):
        import anthropic
        self._raise_on_create(provider, monkeypatch,
            anthropic.RateLimitError("rate limit", response=mock_response, body=None))
        with pytest.raises(LLMRateLimitError):
            provider.complete([LLMMessage(role="user", content="hi")])

    def test_rate_limit_complete_json(self, provider, monkeypatch, mock_response):
        import anthropic
        self._raise_on_create(provider, monkeypatch,
            anthropic.RateLimitError("rate limit", response=mock_response, body=None))
        with pytest.raises(LLMRateLimitError):
            provider.complete_json([LLMMessage(role="user", content="hi")])

    def test_bad_request_context_error(self, provider, monkeypatch, mock_response):
        import anthropic
        self._raise_on_create(provider, monkeypatch,
            anthropic.BadRequestError("maximum context length exceeded with token count", response=mock_response, body=None))
        with pytest.raises(LLMContextError, match="Context window exceeded"):
            provider.complete([LLMMessage(role="user", content="hi")])

    def test_bad_request_context_error_complete_json(self, provider, monkeypatch, mock_response):
        import anthropic
        self._raise_on_create(provider, monkeypatch,
            anthropic.BadRequestError("token limit exceeded", response=mock_response, body=None))
        with pytest.raises(LLMContextError, match="Context window exceeded"):
            provider.complete_json([LLMMessage(role="user", content="hi")])

    def test_bad_request_non_context(self, provider, monkeypatch, mock_response):
        import anthropic
        self._raise_on_create(provider, monkeypatch,
            anthropic.BadRequestError("invalid parameter", response=mock_response, body=None))
        with pytest.raises(LLMError, match="Anthropic API error"):
            provider.complete([LLMMessage(role="user", content="hi")])

    def test_bad_request_non_context_complete_json(self, provider, monkeypatch, mock_response):
        import anthropic
        self._raise_on_create(provider, monkeypatch,
            anthropic.BadRequestError("invalid parameter", response=mock_response, body=None))
        with pytest.raises(LLMError, match="Anthropic API error"):
            provider.complete_json([LLMMessage(role="user", content="hi")])

    def test_api_error_complete(self, provider, monkeypatch, mock_response):
        import anthropic
        self._raise_on_create(provider, monkeypatch,
            anthropic.APIError("server error", request=mock_response.request, body=None))
        with pytest.raises(LLMError, match="Anthropic API error"):
            provider.complete([LLMMessage(role="user", content="hi")])

    def test_api_error_complete_json(self, provider, monkeypatch, mock_response):
        import anthropic
        self._raise_on_create(provider, monkeypatch,
            anthropic.APIError("server error", request=mock_response.request, body=None))
        with pytest.raises(LLMError, match="Anthropic API error"):
            provider.complete_json([LLMMessage(role="user", content="hi")])
