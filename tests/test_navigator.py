"""Tests for knowsql.agent.navigator."""

import json

import pytest

from knowsql.agent.navigator import IndexNavigator


def test_read_file(sample_index_dir):
    nav = IndexNavigator(str(sample_index_dir))
    content = nav.read_file("INDEX.md")
    assert "Database Index" in content


def test_read_file_not_found(sample_index_dir):
    nav = IndexNavigator(str(sample_index_dir))
    result = nav.read_file("nonexistent.md")
    assert "Error" in result
    assert "not found" in result


def test_read_file_section(sample_index_dir):
    nav = IndexNavigator(str(sample_index_dir))
    result = nav.read_file("domains/sales/tables/orders.md", section="Columns")
    assert "## Columns" in result
    assert "customer_id" in result


def test_read_file_section_not_found(sample_index_dir):
    nav = IndexNavigator(str(sample_index_dir))
    result = nav.read_file("INDEX.md", section="NonexistentSection")
    assert "not found" in result


def test_list_directory(sample_index_dir):
    nav = IndexNavigator(str(sample_index_dir))
    result = nav.list_directory("domains/sales/tables")
    assert "orders.md" in result
    assert "customers.md" in result


def test_list_directory_not_found(sample_index_dir):
    nav = IndexNavigator(str(sample_index_dir))
    result = nav.list_directory("nonexistent")
    assert "Error" in result


def test_list_directory_empty(sample_index_dir):
    empty_dir = sample_index_dir / "empty_dir"
    empty_dir.mkdir()
    nav = IndexNavigator(str(sample_index_dir))
    result = nav.list_directory("empty_dir")
    assert result == "(empty directory)"


def test_path_traversal_blocked(sample_index_dir):
    """Bug #5 regression: ../../etc/passwd returns error."""
    nav = IndexNavigator(str(sample_index_dir))
    result = nav.read_file("../../etc/passwd")
    assert "Error" in result
    assert "traversal" in result.lower()


def test_path_traversal_prefix_collision(sample_index_dir):
    """Path that starts with root but escapes via suffix."""
    nav = IndexNavigator(str(sample_index_dir))
    result = nav.read_file("../schema_index_evil/../etc/passwd")
    assert "Error" in result


def test_list_all_tables(sample_index_dir):
    nav = IndexNavigator(str(sample_index_dir))
    tables = nav.list_all_tables()
    assert "orders" in tables
    assert "customers" in tables


def test_list_domains(sample_index_dir):
    nav = IndexNavigator(str(sample_index_dir))
    domains = nav.list_domains()
    assert "sales" in domains


def test_find_and_read_table_exact(sample_index_dir):
    nav = IndexNavigator(str(sample_index_dir))
    content = nav.find_and_read_table("orders")
    assert content is not None
    assert "orders" in content.lower()


def test_find_and_read_table_schema_prefix(sample_index_dir):
    """Bug #12 regression: Find public__orders.md via 'orders'."""
    # Create a schema-prefixed file
    tables_dir = sample_index_dir / "domains" / "sales" / "tables"
    (tables_dir / "public__special.md").write_text("# special\n\nSchema-prefixed table.")

    nav = IndexNavigator(str(sample_index_dir))
    content = nav.find_and_read_table("special")
    assert content is not None
    assert "Schema-prefixed" in content


def test_find_and_read_table_not_found(sample_index_dir):
    nav = IndexNavigator(str(sample_index_dir))
    result = nav.find_and_read_table("nonexistent_table")
    assert result is None


def test_get_dialect_from_meta_json(sample_index_dir):
    """Bug #14 regression: Reads dialect from META.json."""
    nav = IndexNavigator(str(sample_index_dir))
    assert nav.get_dialect() == "sqlite"


def test_get_dialect_fallback_to_index_md(tmp_path):
    """Falls back to INDEX.md heuristic if no META.json."""
    root = tmp_path / "index"
    root.mkdir()
    (root / "INDEX.md").write_text("# Database\n\nThis is a PostgreSQL database.\n")

    nav = IndexNavigator(str(root))
    assert nav.get_dialect() == "postgresql"
