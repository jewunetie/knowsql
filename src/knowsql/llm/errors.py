"""LLM-related error hierarchy."""


class LLMError(Exception):
    """Base error for LLM operations."""
    pass


class LLMAuthError(LLMError):
    """Authentication failed (invalid or missing API key)."""
    pass


class LLMRateLimitError(LLMError):
    """Rate limit exceeded."""
    pass


class LLMContextError(LLMError):
    """Context window exceeded."""
    pass
