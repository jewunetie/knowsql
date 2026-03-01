"""Tests for knowsql.indexer.index_generator."""

import json

import pytest

from knowsql.indexer.index_generator import (
    generate_index, _sanitize, _get_table_filename,
)
from knowsql.indexer.models import (
    DatabaseMetadata, TableMetadata, ColumnMetadata, TableSample,
    Relationship, DomainCluster, ColumnStats,
)
from knowsql.llm.provider import LLMMessage


def _make_table(name, schema=None, ncols=5):
    cols = [ColumnMetadata(name=f"col_{i}", type="TEXT", nullable=True, is_primary_key=(i == 0)) for i in range(ncols)]
    return TableMetadata(name=name, schema=schema, is_view=False, columns=cols, primary_keys=["col_0"], foreign_keys=[], indexes=[], comment=None)


def _make_sample(name, ncols=5):
    stats = {f"col_{i}": ColumnStats(distinct_count=10, null_rate=0.0) for i in range(ncols)}
    return TableSample(table_name=name, row_count=100, sample_rows=[{"col_0": "val"}], column_stats=stats)


def _make_setup(tmp_path, mock_llm, table_names=None, ncols=5):
    """Create a minimal setup for generate_index tests."""
    table_names = table_names or ["orders", "customers"]
    tables = [_make_table(n, ncols=ncols) for n in table_names]
    db = DatabaseMetadata(dialect="sqlite", tables=tables, schemas=[])
    samples = {n: _make_sample(n, ncols=ncols) for n in table_names}
    rels = [
        Relationship(
            source_schema=None, source_table="orders", source_column="customer_id",
            target_schema=None, target_table="customers", target_column="id",
            type="explicit_fk", cardinality="one-to-many",
        ),
    ]
    domains = [DomainCluster(name="sales", description="Sales domain", tables=table_names, also_relevant_to={})]

    # Need LLM responses for: INDEX.md, DOMAIN.md, per-table .md, RELATIONSHIPS.md, GLOSSARY.md
    num_responses = 1 + len(domains) + len(tables) + 2
    llm = mock_llm([LLMMessage(role="assistant", content="# Generated content\nStub documentation.")] * (num_responses + 5))

    output_dir = str(tmp_path / "output")
    return output_dir, db, samples, rels, domains, llm


def test_generate_creates_directory_structure(tmp_path, mock_llm):
    output_dir, db, samples, rels, domains, llm = _make_setup(tmp_path, mock_llm)
    generate_index(output_dir, db, samples, rels, domains, llm)

    from pathlib import Path
    root = Path(output_dir)
    assert (root / "INDEX.md").exists()
    assert (root / "domains").exists()
    assert (root / "cross_references").exists()


def test_meta_json_written(tmp_path, mock_llm):
    """Bug #14 regression: META.json has dialect, schemas, table_count."""
    output_dir, db, samples, rels, domains, llm = _make_setup(tmp_path, mock_llm)
    generate_index(output_dir, db, samples, rels, domains, llm)

    from pathlib import Path
    meta = json.loads((Path(output_dir) / "META.json").read_text())
    assert meta["dialect"] == "sqlite"
    assert "schemas" in meta
    assert meta["table_count"] == 2


def test_domain_directories_created(tmp_path, mock_llm):
    output_dir, db, samples, rels, domains, llm = _make_setup(tmp_path, mock_llm)
    generate_index(output_dir, db, samples, rels, domains, llm)

    from pathlib import Path
    assert (Path(output_dir) / "domains" / "sales").is_dir()


def test_table_files_created(tmp_path, mock_llm):
    output_dir, db, samples, rels, domains, llm = _make_setup(tmp_path, mock_llm)
    generate_index(output_dir, db, samples, rels, domains, llm)

    from pathlib import Path
    tables_dir = Path(output_dir) / "domains" / "sales" / "tables"
    assert (tables_dir / "orders.md").exists()
    assert (tables_dir / "customers.md").exists()


def test_relationships_md_created(tmp_path, mock_llm):
    output_dir, db, samples, rels, domains, llm = _make_setup(tmp_path, mock_llm)
    generate_index(output_dir, db, samples, rels, domains, llm)

    from pathlib import Path
    assert (Path(output_dir) / "cross_references" / "RELATIONSHIPS.md").exists()


def test_glossary_md_created(tmp_path, mock_llm):
    output_dir, db, samples, rels, domains, llm = _make_setup(tmp_path, mock_llm)
    generate_index(output_dir, db, samples, rels, domains, llm)

    from pathlib import Path
    assert (Path(output_dir) / "cross_references" / "GLOSSARY.md").exists()


def test_sanitize_name():
    assert _sanitize("hello world!@#") == "hello_world___"
    assert _sanitize("valid_name-1") == "valid_name-1"


def test_table_filename_single_schema():
    table = _make_table("orders")
    assert _get_table_filename(table, multi_schema=False) == "orders.md"


def test_table_filename_multi_schema():
    table = _make_table("orders", schema="public")
    assert _get_table_filename(table, multi_schema=True) == "public__orders.md"


def test_wide_table_split(tmp_path, mock_llm):
    """More than 80 columns generates _columns_detail.md."""
    output_dir, db, samples, rels, domains, llm = _make_setup(tmp_path, mock_llm, table_names=["wide_table"], ncols=85)
    generate_index(output_dir, db, samples, rels, domains, llm)

    from pathlib import Path
    tables_dir = Path(output_dir) / "domains" / "sales" / "tables"
    assert (tables_dir / "wide_table_columns_detail.md").exists()


def test_progress_callback_called(tmp_path, mock_llm):
    output_dir, db, samples, rels, domains, llm = _make_setup(tmp_path, mock_llm)
    calls = []
    def cb(step, total, desc):
        calls.append((step, total, desc))
    generate_index(output_dir, db, samples, rels, domains, llm, progress_callback=cb)
    assert len(calls) > 0
    # Steps should be sequential
    assert calls[0][0] == 1


def test_returns_stats(tmp_path, mock_llm):
    output_dir, db, samples, rels, domains, llm = _make_setup(tmp_path, mock_llm)
    stats = generate_index(output_dir, db, samples, rels, domains, llm)
    assert stats["table_count"] == 2
    assert stats["domain_count"] == 1
    assert stats["file_count"] > 0
