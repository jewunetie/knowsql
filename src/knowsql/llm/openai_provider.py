"""OpenAI LLM provider."""

import json
import logging

from knowsql.llm.provider import LLMProvider, LLMMessage, ToolCall, ToolDefinition
from knowsql.llm.errors import LLMAuthError, LLMRateLimitError, LLMContextError, LLMError

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self.model = model
        import openai
        self._openai = openai
        self.client = openai.OpenAI(api_key=api_key)

    def complete(self, messages, tools=None, temperature=0.0):
        api_messages = self._prepare_messages(messages)

        kwargs = {
            "model": self.model,
            "temperature": temperature,
            "messages": api_messages,
        }
        if tools:
            kwargs["tools"] = [self._convert_tool(t) for t in tools]

        try:
            response = self.client.chat.completions.create(**kwargs)
        except self._openai.AuthenticationError as e:
            raise LLMAuthError(f"OpenAI authentication failed. Check your API key: {e}")
        except self._openai.RateLimitError as e:
            raise LLMRateLimitError(f"OpenAI rate limit exceeded: {e}")
        except self._openai.BadRequestError as e:
            if "context" in str(e).lower() or "token" in str(e).lower():
                raise LLMContextError(f"Context window exceeded: {e}")
            raise LLMError(f"OpenAI API error: {e}")
        except self._openai.APIError as e:
            raise LLMError(f"OpenAI API error: {e}")

        return self._parse_response(response)

    def complete_json(self, messages, temperature=0.0):
        api_messages = self._prepare_messages(messages)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                messages=api_messages,
                response_format={"type": "json_object"},
            )
        except self._openai.AuthenticationError as e:
            raise LLMAuthError(f"OpenAI authentication failed: {e}")
        except self._openai.RateLimitError as e:
            raise LLMRateLimitError(f"Rate limit exceeded: {e}")
        except self._openai.APIError as e:
            raise LLMError(f"OpenAI API error: {e}")

        text = response.choices[0].message.content or "{}"
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise LLMError(f"Failed to parse JSON response from OpenAI: {text[:200]}")

    def _prepare_messages(self, messages: list[LLMMessage]) -> list[dict]:
        api_messages = []
        for msg in messages:
            if msg.role == "tool":
                api_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content,
                })
            elif msg.role == "assistant" and msg.tool_calls:
                tool_calls = []
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    })
                api_messages.append({
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": tool_calls,
                })
            else:
                api_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })
        return api_messages

    def _convert_tool(self, tool: ToolDefinition) -> dict:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

    def _parse_response(self, response) -> LLMMessage:
        choice = response.choices[0].message
        tool_calls = None

        if choice.tool_calls:
            tool_calls = []
            for tc in choice.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    args = json.loads(args)
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        return LLMMessage(
            role="assistant",
            content=choice.content or "",
            tool_calls=tool_calls,
        )
