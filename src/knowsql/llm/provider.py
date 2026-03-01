"""Core LLM abstractions."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMMessage:
    role: str
    content: str = ""
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict


class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
    ) -> LLMMessage:
        """Send a completion request and return the response."""
        pass

    @abstractmethod
    def complete_json(
        self,
        messages: list[LLMMessage],
        temperature: float | None = None,
    ) -> dict:
        """Send a completion request expecting a JSON response."""
        pass
