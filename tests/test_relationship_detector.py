"""Tests for knowsql.indexer.relationship_detector."""

import pytest

from knowsql.indexer.relationship_detector import (
    detect_relationships, _find_target_table, _infer_cardinality,
)
from knowsql.indexer.models import (
    DatabaseMetadata, TableMetadata, ColumnMetadata, ForeignKey,
)


@pytest.fixture
def relationships(db_metadata):
    return detect_relationships(db_metadata)


def test_explicit_fks_detected(relationships):
    explicit = [r for r in relationships if r.type == "explicit_fk"]
    assert len(explicit) == 17


def test_implicit_relationships_detected(relationships):
    inferred = [r for r in relationships if r.type == "inferred"]
    assert len(inferred) >= 2  # at least customer_segments + product_tags


def test_customer_segments_implicit(relationships):
    matches = [
        r for r in relationships
        if r.source_table == "customer_segments" and r.source_column == "customer_id"
    ]
    assert len(matches) == 1
    assert matches[0].type == "inferred"
    assert matches[0].target_table == "customers"


def test_product_tags_implicit(relationships):
    matches = [
        r for r in relationships
        if r.source_table == "product_tags" and r.source_column == "product_id"
    ]
    assert len(matches) == 1
    assert matches[0].type == "inferred"
    assert matches[0].target_table == "products"


def test_no_self_references_implicit(relationships):
    """Self-referencing columns (categories.parent_category_id) should not appear as implicit."""
    inferred = [r for r in relationships if r.type == "inferred"]
    for r in inferred:
        assert r.source_table != r.target_table


def test_generic_columns_skipped():
    """Generic columns like id, name, status should not trigger implicit detection."""
    table = TableMetadata(
        name="test",
        schema=None,
        is_view=False,
        columns=[
            ColumnMetadata(name="id", type="INTEGER", nullable=False, is_primary_key=True),
            ColumnMetadata(name="name", type="TEXT", nullable=False, is_primary_key=False),
        ],
        primary_keys=["id"],
        foreign_keys=[],
        indexes=[],
        comment=None,
    )
    db = DatabaseMetadata(dialect="sqlite", tables=[table])
    rels = detect_relationships(db)
    assert len(rels) == 0


def test_find_target_exact_match():
    tables = {"customer": TableMetadata(name="customer", schema=None, is_view=False, columns=[], primary_keys=["id"], foreign_keys=[], indexes=[], comment=None)}
    result = _find_target_table("customer", tables)
    assert result is not None
    assert result.name == "customer"


def test_find_target_plural_s():
    tables = {"customers": TableMetadata(name="customers", schema=None, is_view=False, columns=[], primary_keys=["id"], foreign_keys=[], indexes=[], comment=None)}
    result = _find_target_table("customer", tables)
    assert result is not None
    assert result.name == "customers"


def test_find_target_plural_es():
    tables = {"addresses": TableMetadata(name="addresses", schema=None, is_view=False, columns=[], primary_keys=["id"], foreign_keys=[], indexes=[], comment=None)}
    result = _find_target_table("address", tables)
    assert result is not None
    assert result.name == "addresses"


def test_find_target_plural_ies():
    tables = {"categories": TableMetadata(name="categories", schema=None, is_view=False, columns=[], primary_keys=["id"], foreign_keys=[], indexes=[], comment=None)}
    result = _find_target_table("category", tables)
    assert result is not None
    assert result.name == "categories"


def test_find_target_no_match():
    tables = {"orders": TableMetadata(name="orders", schema=None, is_view=False, columns=[], primary_keys=["id"], foreign_keys=[], indexes=[], comment=None)}
    result = _find_target_table("nonexistent", tables)
    assert result is None


def test_cardinality_one_to_many():
    table = TableMetadata(
        name="orders",
        schema=None,
        is_view=False,
        columns=[ColumnMetadata(name="customer_id", type="INTEGER", nullable=False, is_primary_key=False)],
        primary_keys=["id"],
        foreign_keys=[],
        indexes=[],
        comment=None,
    )
    assert _infer_cardinality(table, "customer_id") == "one-to-many"


def test_cardinality_one_to_one():
    table = TableMetadata(
        name="profiles",
        schema=None,
        is_view=False,
        columns=[ColumnMetadata(name="user_id", type="INTEGER", nullable=False, is_primary_key=False)],
        primary_keys=["id"],
        foreign_keys=[],
        indexes=[{"column_names": ["user_id"], "unique": True}],
        comment=None,
    )
    assert _infer_cardinality(table, "user_id") == "one-to-one"


def test_cardinality_many_to_many():
    table = TableMetadata(
        name="order_items",
        schema=None,
        is_view=False,
        columns=[
            ColumnMetadata(name="order_id", type="INTEGER", nullable=False, is_primary_key=True),
            ColumnMetadata(name="product_id", type="INTEGER", nullable=False, is_primary_key=True),
        ],
        primary_keys=["order_id", "product_id"],
        foreign_keys=[
            ForeignKey(source_column="order_id", target_schema=None, target_table="orders", target_column="id"),
            ForeignKey(source_column="product_id", target_schema=None, target_table="products", target_column="id"),
        ],
        indexes=[],
        comment=None,
    )
    assert _infer_cardinality(table, "order_id") == "many-to-many"


def test_explicit_not_duplicated(relationships):
    """Explicit FK should not also appear as implicit."""
    seen = set()
    for r in relationships:
        key = (r.source_table, r.source_column, r.target_table, r.target_column)
        assert key not in seen, f"Duplicate relationship: {key}"
        seen.add(key)


def test_total_relationship_count(relationships):
    # 17 explicit + inferred (at least 2-3)
    assert len(relationships) == 20
