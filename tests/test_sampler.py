"""Tests for knowsql.indexer.sampler."""

import pytest

from knowsql.indexer.sampler import sample_tables, _serialize_value
from knowsql.indexer.models import TableMetadata, ColumnMetadata


def test_sample_full_mode(dummy_db, db_metadata):
    results = sample_tables(dummy_db, db_metadata.tables, sample_rows=3, sample_mode="full")
    orders = results["orders"]
    assert orders.sample_rows  # should have sample rows
    assert orders.column_stats  # should have stats


def test_sample_schema_only_mode(dummy_db, db_metadata):
    results = sample_tables(dummy_db, db_metadata.tables, sample_rows=3, sample_mode="schema-only")
    orders = results["orders"]
    assert orders.sample_rows == []  # no sample rows in schema-only
    assert orders.column_stats  # should still have column stats


def test_sample_none_mode(dummy_db, db_metadata):
    results = sample_tables(dummy_db, db_metadata.tables, sample_mode="none")
    assert results == {}


def test_row_count_populated(dummy_db, db_metadata):
    results = sample_tables(dummy_db, db_metadata.tables, sample_mode="full")
    assert results["orders"].row_count > 0
    assert results["customers"].row_count > 0


def test_distinct_count(dummy_db, db_metadata):
    results = sample_tables(dummy_db, db_metadata.tables, sample_mode="full")
    stats = results["customers"].column_stats
    assert stats["email"].distinct_count > 0


def test_null_rate(dummy_db, db_metadata):
    results = sample_tables(dummy_db, db_metadata.tables, sample_mode="full")
    stats = results["orders"].column_stats
    # null_rate is a percentage between 0 and 100
    for col_name, col_stats in stats.items():
        assert 0 <= col_stats.null_rate <= 100


def test_enum_detection(dummy_db, db_metadata):
    results = sample_tables(dummy_db, db_metadata.tables, sample_mode="full")
    stats = results["orders"].column_stats
    # orders.status is low cardinality -> should have enum_values
    assert stats["status"].enum_values is not None
    assert len(stats["status"].enum_values) > 0


def test_enum_only_in_full_mode(dummy_db, db_metadata):
    results = sample_tables(dummy_db, db_metadata.tables, sample_mode="schema-only")
    stats = results["orders"].column_stats
    assert stats["status"].enum_values is None


def test_sample_rows_limit(dummy_db, db_metadata):
    results = sample_tables(dummy_db, db_metadata.tables, sample_rows=3, sample_mode="full")
    assert len(results["orders"].sample_rows) <= 3


def test_serialize_value_none():
    assert _serialize_value(None) == "NULL"


def test_serialize_value_string():
    assert _serialize_value("hello") == "hello"


def test_progress_callback(dummy_db, db_metadata):
    calls = []
    def cb(current, total, name):
        calls.append((current, total, name))
    sample_tables(dummy_db, db_metadata.tables, sample_mode="full", progress_callback=cb)
    assert len(calls) == len(db_metadata.tables)
    # First call should be (1, total, some_name)
    assert calls[0][0] == 1
    assert calls[0][1] == len(db_metadata.tables)


def test_empty_table_handling(dummy_db):
    """Table with 0 rows returns row_count=0, empty sample_rows."""
    # Create a metadata object for an empty table scenario
    empty_table = TableMetadata(
        name="nonexistent_empty",
        schema=None,
        is_view=False,
        columns=[ColumnMetadata(name="id", type="INTEGER", nullable=False, is_primary_key=True)],
        primary_keys=["id"],
        foreign_keys=[],
        indexes=[],
        comment=None,
    )
    # This will fail to sample since the table doesn't exist in DB -> fallback to empty
    results = sample_tables(dummy_db, [empty_table], sample_mode="full")
    assert results["nonexistent_empty"].row_count == 0
    assert results["nonexistent_empty"].sample_rows == []


def test_engine_disposed(dummy_db, db_metadata, monkeypatch):
    """Bug #10 regression: Engine should be disposed after sampling."""
    disposed = []

    from sqlalchemy import create_engine as real_create_engine

    def tracking_create_engine(conn_str):
        engine = real_create_engine(conn_str)
        original_dispose = engine.dispose
        def tracked_dispose():
            disposed.append(True)
            original_dispose()
        engine.dispose = tracked_dispose
        return engine

    monkeypatch.setattr("knowsql.indexer.sampler.create_engine", tracking_create_engine)
    sample_tables(dummy_db, db_metadata.tables[:1], sample_mode="full")
    assert len(disposed) == 1
