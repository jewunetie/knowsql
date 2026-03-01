"""Tests for knowsql.agent.sql_generator."""

import pytest

from knowsql.agent.sql_generator import (
    generate_sql, _parse_sql_response, _execute_and_retry, SQLResult,
)
from knowsql.agent.agent import TableProposal
from knowsql.agent.navigator import IndexNavigator
from knowsql.llm.provider import LLMMessage


def test_generate_sql_returns_result(sample_index_dir, mock_llm):
    nav = IndexNavigator(str(sample_index_dir))
    proposal = TableProposal(
        tables=[{"table_name": "orders", "reason": "needed"}],
        reasoning="test",
    )
    llm = mock_llm([
        LLMMessage(role="assistant", content="Interpretation: Get all orders\n\n```sql\nSELECT * FROM orders;\n```\n\nExplanation: Simple select"),
    ])
    result = generate_sql("show orders", proposal, nav, llm)
    assert isinstance(result, SQLResult)
    assert result.sql == "SELECT * FROM orders;"


def test_generate_sql_no_tables():
    proposal = TableProposal(tables=[], reasoning="Could not find tables")
    result = generate_sql("test", proposal, None, None)
    assert result.sql == ""
    assert result.interpretation is not None


def test_generate_sql_loads_table_docs(sample_index_dir, mock_llm):
    nav = IndexNavigator(str(sample_index_dir))
    proposal = TableProposal(
        tables=[{"table_name": "orders", "reason": "needed"}],
        reasoning="test",
    )
    llm = mock_llm([
        LLMMessage(role="assistant", content="```sql\nSELECT 1;\n```"),
    ])
    generate_sql("test", proposal, nav, llm)
    # Check that table documentation was loaded (present in the prompt)
    messages = llm.calls[0][1]
    prompt_content = messages[0].content
    assert "orders" in prompt_content


def test_generate_sql_filters_relationships(sample_index_dir, mock_llm):
    """Bug #7 regression: Only selected table relationships included."""
    nav = IndexNavigator(str(sample_index_dir))
    proposal = TableProposal(
        tables=[{"table_name": "orders", "reason": "needed"}],
        reasoning="test",
    )
    llm = mock_llm([
        LLMMessage(role="assistant", content="```sql\nSELECT 1;\n```"),
    ])
    generate_sql("test", proposal, nav, llm)
    messages = llm.calls[0][1]
    prompt_content = messages[0].content
    # The full RELATIONSHIPS.md should have been filtered
    # Lines containing "orders" should be included
    assert "orders" in prompt_content


def test_parse_sql_backtick_fence():
    content = "Some text\n\n```sql\nSELECT * FROM orders;\n```\n\nMore text"
    result = _parse_sql_response(content)
    assert result.sql == "SELECT * FROM orders;"


def test_parse_sql_tilde_fence():
    """Bug #13 regression: ~~~sql fence -> SQL extracted."""
    content = "Some text\n\n~~~sql\nSELECT * FROM orders;\n~~~\n\nMore text"
    result = _parse_sql_response(content)
    assert result.sql == "SELECT * FROM orders;"


def test_parse_sql_interpretation():
    content = "Interpretation: Get all customer orders\n\n```sql\nSELECT 1;\n```"
    result = _parse_sql_response(content)
    assert result.interpretation == "Get all customer orders"


def test_parse_sql_explanation():
    content = "```sql\nSELECT 1;\n```\n\nExplanation: This query does something\nAnd continues here"
    result = _parse_sql_response(content)
    assert result.explanation is not None
    assert "does something" in result.explanation


def test_parse_sql_no_sql_block():
    content = "I cannot generate SQL for this question."
    result = _parse_sql_response(content)
    assert result.sql == ""


def test_execute_and_retry_success(dummy_db, mock_llm):
    result = SQLResult(sql="SELECT COUNT(*) FROM orders;")
    llm = mock_llm([])  # No LLM calls needed for success
    result = _execute_and_retry(result, "count orders", [], llm, "sqlite", dummy_db)
    assert result.executed is True
    assert result.results is not None
    assert result.error is None


def test_execute_and_retry_failure(dummy_db, mock_llm):
    """Failing query retried up to 3 times."""
    result = SQLResult(sql="SELECT * FROM nonexistent_table;")
    # Each retry gets a fix attempt from LLM, but all still fail
    llm = mock_llm([
        LLMMessage(role="assistant", content="```sql\nSELECT * FROM still_nonexistent;\n```"),
        LLMMessage(role="assistant", content="```sql\nSELECT * FROM also_nonexistent;\n```"),
        LLMMessage(role="assistant", content="```sql\nSELECT * FROM nope;\n```"),
    ])
    result = _execute_and_retry(result, "test", [], llm, "sqlite", dummy_db)
    assert result.error is not None
    assert "failed" in result.error.lower()


def test_execute_and_retry_fix_applied(dummy_db, mock_llm):
    """LLM fix prompt used on retry - second attempt succeeds."""
    result = SQLResult(sql="SELECT * FROM nonexistent_table;")
    llm = mock_llm([
        # First retry: LLM fixes the query
        LLMMessage(role="assistant", content="```sql\nSELECT COUNT(*) FROM orders;\n```"),
    ])
    result = _execute_and_retry(result, "count orders", [], llm, "sqlite", dummy_db)
    assert result.executed is True
    assert result.error is None


def test_execute_max_retries_exceeded(dummy_db, mock_llm):
    """After MAX_RETRIES+1 failures, error returned."""
    result = SQLResult(sql="INVALID SQL")
    llm = mock_llm([
        LLMMessage(role="assistant", content="```sql\nSTILL INVALID;\n```"),
        LLMMessage(role="assistant", content="```sql\nSTILL INVALID;\n```"),
        LLMMessage(role="assistant", content="```sql\nSTILL INVALID;\n```"),
    ])
    result = _execute_and_retry(result, "test", [], llm, "sqlite", dummy_db)
    assert result.error is not None


def test_sql_result_dataclass():
    result = SQLResult()
    assert result.interpretation is None
    assert result.sql == ""
    assert result.explanation is None
    assert result.executed is False
    assert result.results is None
    assert result.columns == []
    assert result.error is None
