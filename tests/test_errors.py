"""Tests for knowsql.llm.errors."""

from knowsql.llm.errors import LLMError, LLMAuthError, LLMRateLimitError, LLMContextError


def test_error_hierarchy():
    assert issubclass(LLMAuthError, LLMError)
    assert issubclass(LLMRateLimitError, LLMError)
    assert issubclass(LLMContextError, LLMError)


def test_errors_are_exceptions():
    for cls in (LLMError, LLMAuthError, LLMRateLimitError, LLMContextError):
        assert issubclass(cls, Exception)


def test_error_message():
    e = LLMAuthError("bad key")
    assert str(e) == "bad key"


def test_catch_base_catches_subtypes():
    for cls in (LLMAuthError, LLMRateLimitError, LLMContextError):
        try:
            raise cls("test")
        except LLMError:
            pass  # should be caught
        else:
            raise AssertionError(f"{cls.__name__} not caught by LLMError")
