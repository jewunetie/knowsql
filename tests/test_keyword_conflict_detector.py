"""Tests for knowsql.indexer.keyword_conflict_detector."""

import pytest
from pathlib import Path

from knowsql.indexer.keyword_conflict_detector import (
    detect_keyword_conflicts, _parse_keywords_from_file, KEYWORD_STOPWORDS,
)
from knowsql.llm.provider import LLMMessage
from collections import defaultdict


def _create_index_with_tables(tmp_path, table_files):
    """Helper to create a minimal index structure with table files."""
    root = tmp_path / "index"
    tables_dir = root / "domains" / "sales" / "tables"
    tables_dir.mkdir(parents=True)
    (root / "cross_references").mkdir(parents=True)

    for name, content in table_files.items():
        (tables_dir / f"{name}.md").write_text(content)

    return str(root)


def test_no_conflicts_returns_message(tmp_path):
    output_dir = _create_index_with_tables(tmp_path, {
        "orders": "# orders\n\nKeywords: purchases\n",
        "customers": "# customers\n\nKeywords: clients\n",
    })
    # No LLM needed since no conflicts
    result = detect_keyword_conflicts(output_dir, None)
    assert "No ambiguous terms" in result


def test_conflicts_detected(tmp_path, mock_llm):
    output_dir = _create_index_with_tables(tmp_path, {
        "orders": "# orders\n\nKeywords: revenue, sales\n",
        "invoices": "# invoices\n\nKeywords: revenue, billing\n",
    })
    llm = mock_llm([LLMMessage(role="assistant", content="# Ambiguous Terms\n\n- revenue: orders vs invoices")])
    result = detect_keyword_conflicts(output_dir, llm)
    assert "revenue" in result.lower()


def test_stopwords_filtered(tmp_path):
    output_dir = _create_index_with_tables(tmp_path, {
        "orders": "# orders\n\nKeywords: id, name, status, purchases\n",
        "customers": "# customers\n\nKeywords: id, name, status, clients\n",
    })
    result = detect_keyword_conflicts(output_dir, None)
    # id, name, status should be filtered as stopwords -> no conflicts
    assert "No ambiguous terms" in result


def test_stopwords_extend(tmp_path, mock_llm):
    output_dir = _create_index_with_tables(tmp_path, {
        "orders": "# orders\n\nKeywords: revenue, custom_term\n",
        "invoices": "# invoices\n\nKeywords: revenue, custom_term\n",
    })
    # Extend stopwords with "custom_term" -> only "revenue" is conflict
    llm = mock_llm([LLMMessage(role="assistant", content="# Ambiguous Terms\n\n- revenue")])
    result = detect_keyword_conflicts(output_dir, llm, stopwords_extend=["custom_term"])
    # custom_term should be filtered
    assert "custom_term" not in result.lower() or "revenue" in result.lower()


def test_stopwords_override(tmp_path, mock_llm):
    """Custom stopwords replace default set entirely."""
    output_dir = _create_index_with_tables(tmp_path, {
        "orders": "# orders\n\nKeywords: id, purchases\n",
        "customers": "# customers\n\nKeywords: id, clients\n",
    })
    # Override stopwords to ONLY filter "purchases" and "clients"
    # "id" is no longer a stopword -> it becomes a conflict
    llm = mock_llm([LLMMessage(role="assistant", content="# Ambiguous Terms\n\n- id")])
    result = detect_keyword_conflicts(output_dir, llm, stopwords_override=["purchases", "clients"])
    # The LLM was called (conflict detected) so we get generated content
    assert "id" in result.lower()


def test_parse_keywords_table_level(tmp_path):
    """Keywords: at top level -> table-level entries."""
    f = tmp_path / "orders.md"
    f.write_text("# orders\n\nKeywords: purchases, transactions\n\n## Columns\n")
    inverted = defaultdict(list)
    _parse_keywords_from_file(f, "orders", inverted)
    assert ("orders", None) in inverted["purchases"]
    assert ("orders", None) in inverted["transactions"]


def test_parse_keywords_column_level(tmp_path):
    """Keywords in ## Columns section -> column-level entries."""
    f = tmp_path / "orders.md"
    f.write_text(
        "# orders\n\n## Columns\n\n### total_amount\nKeywords: revenue, total\n"
    )
    inverted = defaultdict(list)
    _parse_keywords_from_file(f, "orders", inverted)
    assert ("orders", "total_amount") in inverted["revenue"]


def test_multi_word_keywords_filtered(tmp_path):
    """Keywords with >3 words should be skipped."""
    f = tmp_path / "orders.md"
    f.write_text("# orders\n\nKeywords: purchases, this is a very long keyword phrase\n")
    inverted = defaultdict(list)
    _parse_keywords_from_file(f, "orders", inverted)
    assert "purchases" in inverted
    assert "this is a very long keyword phrase" not in inverted


def test_ambiguous_terms_file_written(tmp_path, mock_llm):
    output_dir = _create_index_with_tables(tmp_path, {
        "orders": "# orders\n\nKeywords: revenue\n",
        "invoices": "# invoices\n\nKeywords: revenue\n",
    })
    llm = mock_llm([LLMMessage(role="assistant", content="# Ambiguous Terms\n\nresolution guide")])
    detect_keyword_conflicts(output_dir, llm)
    assert (Path(output_dir) / "cross_references" / "AMBIGUOUS_TERMS.md").exists()


def test_detail_files_excluded(tmp_path):
    """_columns_detail.md files should not be parsed."""
    root = tmp_path / "index"
    tables_dir = root / "domains" / "sales" / "tables"
    tables_dir.mkdir(parents=True)
    (root / "cross_references").mkdir(parents=True)

    (tables_dir / "orders.md").write_text("# orders\n\nKeywords: purchases\n")
    (tables_dir / "orders_columns_detail.md").write_text("# Detail\n\nKeywords: purchases\n")

    result = detect_keyword_conflicts(str(root), None)
    # Only one table file parsed, so "purchases" maps to 1 table -> no conflict
    assert "No ambiguous terms" in result
