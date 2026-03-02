"""OpenAI LLM provider (Responses API)."""

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

    def complete(self, messages, tools=None, temperature=None):
        input_items, instructions = self._prepare_input(messages)

        kwargs = {
            "model": self.model,
            "input": input_items,
        }
        if instructions:
            kwargs["instructions"] = instructions
        if temperature is not None:
            kwargs["temperature"] = temperature
        if tools:
            kwargs["tools"] = [self._convert_tool(t) for t in tools]

        try:
            response = self.client.responses.create(**kwargs)
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

    def complete_json(self, messages, temperature=None):
        input_items, instructions = self._prepare_input(messages)

        kwargs = {
            "model": self.model,
            "input": input_items,
            "text": {"format": {"type": "json_object"}},
        }
        if instructions:
            kwargs["instructions"] = instructions
        if temperature is not None:
            kwargs["temperature"] = temperature

        try:
            response = self.client.responses.create(**kwargs)
        except self._openai.AuthenticationError as e:
            raise LLMAuthError(f"OpenAI authentication failed: {e}")
        except self._openai.RateLimitError as e:
            raise LLMRateLimitError(f"Rate limit exceeded: {e}")
        except self._openai.APIError as e:
            raise LLMError(f"OpenAI API error: {e}")

        text = response.output_text or "{}"
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise LLMError(f"Failed to parse JSON response from OpenAI: {text[:200]}")

    def _prepare_input(self, messages: list[LLMMessage]) -> tuple[list[dict], str | None]:
        """Convert LLMMessages to Responses API input items + instructions.

        Returns (input_items, instructions) where instructions is extracted
        from system messages (or None if no system messages).
        """
        input_items = []
        instructions = None

        for msg in messages:
            if msg.role == "system":
                instructions = msg.content
            elif msg.role == "tool":
                input_items.append({
                    "type": "function_call_output",
                    "call_id": msg.tool_call_id,
                    "output": msg.content,
                })
            elif msg.role == "assistant" and msg.tool_calls:
                if msg.content:
                    input_items.append({
                        "role": "assistant",
                        "content": msg.content,
                    })
                for tc in msg.tool_calls:
                    input_items.append({
                        "type": "function_call",
                        "call_id": tc.id,
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    })
            else:
                input_items.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        return input_items, instructions

    def _convert_tool(self, tool: ToolDefinition) -> dict:
        return {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            "strict": False,
        }

    def _parse_response(self, response) -> LLMMessage:
        tool_calls = None

        fc_items = [item for item in response.output if item.type == "function_call"]
        if fc_items:
            tool_calls = []
            for item in fc_items:
                args = item.arguments
                if isinstance(args, str):
                    args = json.loads(args)
                tool_calls.append(ToolCall(
                    id=item.call_id,
                    name=item.name,
                    arguments=args,
                ))

        return LLMMessage(
            role="assistant",
            content=response.output_text or "",
            tool_calls=tool_calls,
        )
