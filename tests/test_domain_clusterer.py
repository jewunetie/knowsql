"""Tests for knowsql.indexer.domain_clusterer."""

import pytest

from knowsql.indexer.domain_clusterer import (
    cluster_domains, _validate_mece, _format_domains_for_merge, _cluster_batch,
    BATCH_SIZE,
)
from knowsql.indexer.models import (
    DatabaseMetadata, TableMetadata, ColumnMetadata, DomainCluster,
)
from knowsql.llm.provider import LLMMessage


def _make_table(name, cols=None):
    cols = cols or ["id", "name"]
    return TableMetadata(
        name=name,
        schema=None,
        is_view=False,
        columns=[ColumnMetadata(name=c, type="TEXT", nullable=True, is_primary_key=(c == "id")) for c in cols],
        primary_keys=["id"],
        foreign_keys=[],
        indexes=[],
        comment=None,
    )


def _make_db(table_names):
    tables = [_make_table(n) for n in table_names]
    return DatabaseMetadata(dialect="sqlite", tables=tables)


def test_cluster_returns_domain_clusters(db_metadata, mock_llm):
    llm = mock_llm([
        {"domains": {"sales": {"description": "Sales stuff", "tables": [t.name for t in db_metadata.tables], "also_relevant_to": {}}}},
    ])
    result = cluster_domains(db_metadata, llm)
    assert all(isinstance(c, DomainCluster) for c in result)


def test_all_tables_assigned(db_metadata, mock_llm):
    all_names = {t.name for t in db_metadata.tables}
    llm = mock_llm([
        {"domains": {"sales": {"description": "All", "tables": list(all_names), "also_relevant_to": {}}}},
    ])
    result = cluster_domains(db_metadata, llm)
    assigned = set()
    for cluster in result:
        assigned.update(cluster.tables)
    assert assigned == all_names


def test_no_duplicate_tables(db_metadata, mock_llm):
    all_names = [t.name for t in db_metadata.tables]
    half = len(all_names) // 2
    llm = mock_llm([
        {"domains": {
            "a": {"description": "A", "tables": all_names[:half], "also_relevant_to": {}},
            "b": {"description": "B", "tables": all_names[half:], "also_relevant_to": {}},
        }},
    ])
    result = cluster_domains(db_metadata, llm)
    seen = set()
    for cluster in result:
        for t in cluster.tables:
            assert t not in seen, f"Duplicate: {t}"
            seen.add(t)


def test_no_empty_domains(db_metadata, mock_llm):
    all_names = [t.name for t in db_metadata.tables]
    llm = mock_llm([
        {"domains": {"sales": {"description": "All", "tables": all_names, "also_relevant_to": {}}}},
    ])
    result = cluster_domains(db_metadata, llm)
    for cluster in result:
        assert len(cluster.tables) > 0


def test_validate_mece_missing_tables(mock_llm):
    llm = mock_llm([
        {"assignments": {"c": "group1"}},
    ])
    domains = {"group1": {"description": "G1", "tables": ["a", "b"], "also_relevant_to": {}}}
    all_names = {"a", "b", "c"}
    tables = [_make_table(n) for n in all_names]
    result = _validate_mece(domains, all_names, tables, llm)
    assigned = set()
    for info in result.values():
        assigned.update(info["tables"])
    assert "c" in assigned


def test_validate_mece_duplicate_tables():
    """Duplicates resolved: first assignment wins."""
    domains = {
        "a": {"tables": ["t1", "t2"]},
        "b": {"tables": ["t2", "t3"]},
    }
    from knowsql.indexer.domain_clusterer import _validate_mece
    # No missing tables so LLM won't be called
    result = _validate_mece(domains, {"t1", "t2", "t3"}, [], None)
    # t2 should only appear in domain "a" (first seen)
    assert "t2" in result["a"]["tables"]
    assert "t2" not in result["b"]["tables"]


def test_validate_mece_empty_domain_removed():
    domains = {
        "a": {"tables": ["t1"]},
        "b": {"tables": []},
    }
    result = _validate_mece(domains, {"t1"}, [], None)
    assert "b" not in result


def test_large_db_batching(mock_llm):
    """More than BATCH_SIZE*2 tables triggers batch mode."""
    names = [f"table_{i}" for i in range(BATCH_SIZE * 2 + 10)]
    db = _make_db(names)

    # Need responses for: batch1 + batch2 + batch3 + merge + (possibly MECE fix)
    batch_response = {"domains": {"all": {"description": "All tables", "tables": names, "also_relevant_to": {}}}}
    llm = mock_llm([batch_response] * 5)
    result = cluster_domains(db, llm)
    assert len(result) > 0


def test_cluster_batch_handles_missing_keys(mock_llm):
    """Bug #6 regression: .get() handles missing description/tables."""
    llm = mock_llm([
        {"domains": {"sales": {}}},  # missing description and tables keys
    ])
    tables = [_make_table("orders")]
    result = _cluster_batch(tables, llm)
    assert "sales" in result


def test_format_domains_for_merge():
    domains = {
        "sales": {
            "description": "Sales domain",
            "tables": [f"t{i}" for i in range(15)],
        },
    }
    result = _format_domains_for_merge(domains)
    assert "+5 more" in result
