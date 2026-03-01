"""Tests for knowsql.indexer.introspector using the dummy SQLite database."""

from knowsql.indexer.models import DatabaseMetadata


def test_introspect_returns_metadata(db_metadata):
    assert isinstance(db_metadata, DatabaseMetadata)


def test_dialect_is_sqlite(db_metadata):
    assert db_metadata.dialect == "sqlite"


def test_table_count(db_metadata):
    # 18 tables + 2 views = 20
    assert len(db_metadata.tables) == 20


def test_view_detection(db_metadata):
    views = [t for t in db_metadata.tables if t.is_view]
    view_names = {v.name for v in views}
    assert "revenue_summary" in view_names
    assert "customer_lifetime_value" in view_names
    assert len(views) == 2


def test_views_have_no_fks(db_metadata):
    views = [t for t in db_metadata.tables if t.is_view]
    for v in views:
        assert v.foreign_keys == []


def test_views_have_no_pks(db_metadata):
    views = [t for t in db_metadata.tables if t.is_view]
    for v in views:
        assert v.primary_keys == []


def test_table_has_columns(db_metadata):
    orders = next(t for t in db_metadata.tables if t.name == "orders")
    col_names = {c.name for c in orders.columns}
    assert "id" in col_names
    assert "customer_id" in col_names
    assert "total_amount" in col_names
    assert "status" in col_names


def test_primary_keys(db_metadata):
    orders = next(t for t in db_metadata.tables if t.name == "orders")
    assert orders.primary_keys == ["id"]


def test_foreign_keys(db_metadata):
    orders = next(t for t in db_metadata.tables if t.name == "orders")
    fk_targets = {(fk.target_table, fk.target_column) for fk in orders.foreign_keys}
    assert ("customers", "id") in fk_targets


def test_column_types(db_metadata):
    orders = next(t for t in db_metadata.tables if t.name == "orders")
    for col in orders.columns:
        assert col.type  # type string should be populated


def test_fk_less_tables(db_metadata):
    for name in ("customer_segments", "product_tags"):
        table = next(t for t in db_metadata.tables if t.name == name)
        assert table.foreign_keys == [], f"{name} should have no FK constraints"


def test_schema_is_none_for_sqlite(db_metadata):
    for table in db_metadata.tables:
        assert table.schema is None
