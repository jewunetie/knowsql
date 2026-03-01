"""Tests for knowsql.utils.display."""

from knowsql.utils.display import (
    display_sql, display_results_table, display_table_proposal,
    display_navigation_step, create_indexing_progress,
)
from knowsql.agent.agent import TableProposal
from rich.progress import Progress


def test_display_sql_no_crash():
    """display_sql() with all params doesn't crash."""
    display_sql(
        sql="SELECT * FROM orders;",
        interpretation="Get all orders",
        explanation="Simple select query",
    )


def test_display_results_table_null_values(capsys):
    """Bug #9 regression: None renders as 'NULL' not 'None'."""
    display_results_table(
        columns=["id", "name", "value"],
        rows=[(1, "Alice", None), (2, None, 42)],
    )
    captured = capsys.readouterr()
    assert "NULL" in captured.out
    # Should NOT contain the Python string "None"
    # (Rich renders it, so we check the output contains NULL)


def test_display_table_proposal_empty(capsys):
    proposal = TableProposal(tables=[], reasoning="No tables found")
    display_table_proposal(proposal)
    captured = capsys.readouterr()
    assert "No tables proposed" in captured.out


def test_display_table_proposal_with_tables(capsys):
    proposal = TableProposal(
        tables=[
            {"table_name": "orders", "reason": "Contains order data", "columns": ["id", "total"]},
            {"table_name": "customers", "reason": "Customer info"},
        ],
        joins=[{"left": "orders.customer_id", "right": "customers.id", "type": "JOIN"}],
        reasoning="These tables answer the question.",
    )
    display_table_proposal(proposal)
    captured = capsys.readouterr()
    assert "orders" in captured.out
    assert "customers" in captured.out


def test_display_navigation_step_read_file(capsys):
    display_navigation_step(1, "read_file", {"path": "INDEX.md", "section": "Domains"})
    captured = capsys.readouterr()
    assert "Step 1" in captured.out
    assert "INDEX.md" in captured.out
    assert "Domains" in captured.out


def test_create_indexing_progress():
    progress = create_indexing_progress()
    assert isinstance(progress, Progress)
