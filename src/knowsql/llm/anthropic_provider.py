"""Anthropic (Claude) LLM provider."""

import json
import logging

from knowsql.llm.provider import LLMProvider, LLMMessage, ToolCall, ToolDefinition
from knowsql.llm.errors import LLMAuthError, LLMRateLimitError, LLMContextError, LLMError

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self.model = model
        import anthropic
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key)

    def complete(self, messages, tools=None, temperature=0.0):
        api_messages, system = self._prepare_messages(messages)

        kwargs = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": temperature,
            "messages": api_messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [self._convert_tool(t) for t in tools]

        try:
            response = self.client.messages.create(**kwargs)
        except self._anthropic.AuthenticationError as e:
            raise LLMAuthError(f"Anthropic authentication failed. Check your API key: {e}")
        except self._anthropic.RateLimitError as e:
            raise LLMRateLimitError(f"Anthropic rate limit exceeded: {e}")
        except self._anthropic.BadRequestError as e:
            if "context" in str(e).lower() or "token" in str(e).lower():
                raise LLMContextError(f"Context window exceeded: {e}")
            raise LLMError(f"Anthropic API error: {e}")
        except self._anthropic.APIError as e:
            raise LLMError(f"Anthropic API error: {e}")

        return self._parse_response(response)

    def complete_json(self, messages, temperature=0.0):
        # Use assistant prefill with { to encourage JSON
        api_messages, system = self._prepare_messages(messages)
        api_messages.append({"role": "assistant", "content": "{"})

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=temperature,
                messages=api_messages,
                system=system or "",
            )
        except self._anthropic.AuthenticationError as e:
            raise LLMAuthError(f"Anthropic authentication failed: {e}")
        except self._anthropic.RateLimitError as e:
            raise LLMRateLimitError(f"Rate limit exceeded: {e}")
        except self._anthropic.APIError as e:
            raise LLMError(f"Anthropic API error: {e}")

        raw = self._extract_text(response).strip()
        text = "{" + raw
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Fallback: the LLM may have included the opening brace itself
            if raw.startswith("{"):
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    pass
            raise LLMError(f"Failed to parse JSON response from Anthropic: {text[:200]}")

    def _prepare_messages(self, messages: list[LLMMessage]):
        """Convert LLMMessages to Anthropic API format, extracting system message."""
        system = None
        api_messages = []

        for msg in messages:
            if msg.role == "system":
                system = msg.content
                continue

            if msg.role == "tool":
                # Tool results go as user messages with tool_result content blocks
                api_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }],
                })
            elif msg.role == "assistant" and msg.tool_calls:
                content = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                api_messages.append({"role": "assistant", "content": content})
            else:
                api_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        # Merge consecutive same-role messages
        api_messages = self._merge_consecutive_roles(api_messages)

        return api_messages, system

    def _merge_consecutive_roles(self, messages):
        """Merge consecutive messages with the same role (Anthropic requirement)."""
        if not messages:
            return messages

        merged = [dict(messages[0])]
        for msg in messages[1:]:
            if msg["role"] == merged[-1]["role"]:
                prev_content = merged[-1]["content"]
                curr_content = msg["content"]

                # Normalize to list of content blocks
                if isinstance(prev_content, str):
                    prev_content = [{"type": "text", "text": prev_content}]
                if isinstance(curr_content, str):
                    curr_content = [{"type": "text", "text": curr_content}]
                if isinstance(prev_content, dict):
                    prev_content = [prev_content]
                if isinstance(curr_content, dict):
                    curr_content = [curr_content]

                merged[-1]["content"] = prev_content + curr_content
            else:
                merged.append(msg)

        return merged

    def _convert_tool(self, tool: ToolDefinition) -> dict:
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.parameters,
        }

    def _parse_response(self, response) -> LLMMessage:
        text_parts = []
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input,  # Already a dict
                ))

        return LLMMessage(
            role="assistant",
            content="\n".join(text_parts),
            tool_calls=tool_calls if tool_calls else None,
        )

    def _extract_text(self, response) -> str:
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""
