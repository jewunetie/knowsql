"""Foreign key and implicit relationship detection."""

import logging
import re

from knowsql.indexer.models import DatabaseMetadata, TableMetadata, Relationship

logger = logging.getLogger(__name__)

# Generic column names that should NOT trigger implicit relationship detection
GENERIC_COLUMNS = {
    "id", "name", "type", "status", "code", "value", "key", "data", "info",
    "description", "label", "title", "created_at", "updated_at", "deleted_at",
    "created_by", "updated_by", "is_active", "is_deleted", "sort_order",
    "position", "version", "notes", "comment", "metadata",
}


def detect_relationships(db_metadata: DatabaseMetadata) -> list[Relationship]:
    """Detect all relationships (explicit FKs + implicit heuristics)."""
    relationships = []

    # Build lookup tables
    table_names = {t.name.lower(): t for t in db_metadata.tables}
    # Track explicit FKs to avoid duplicates
    explicit_pairs = set()

    # Step 1: Explicit FKs from introspection
    for table in db_metadata.tables:
        for fk in table.foreign_keys:
            rel = Relationship(
                source_schema=table.schema,
                source_table=table.name,
                source_column=fk.source_column,
                target_schema=fk.target_schema,
                target_table=fk.target_table,
                target_column=fk.target_column,
                type="explicit_fk",
                cardinality=_infer_cardinality(table, fk.source_column),
            )
            relationships.append(rel)
            explicit_pairs.add((
                table.name.lower(), fk.source_column.lower(),
                fk.target_table.lower(), fk.target_column.lower(),
            ))

    # Step 2: Implicit relationships
    for table in db_metadata.tables:
        for col in table.columns:
            col_lower = col.name.lower()

            # Skip generic columns
            if col_lower in GENERIC_COLUMNS:
                continue

            # Match {X}_id pattern
            if not col_lower.endswith("_id"):
                continue

            prefix = col_lower[:-3]  # Remove _id
            if not prefix or prefix == "":
                continue

            # Try to find a matching table
            target_table = _find_target_table(prefix, table_names)
            if not target_table:
                continue

            # Don't create self-references unless they're explicit
            if target_table.name.lower() == table.name.lower():
                continue

            # Determine target column (usually 'id' or the PK)
            target_col = "id"
            if target_table.primary_keys:
                target_col = target_table.primary_keys[0]

            # Skip if already covered by explicit FK
            pair = (
                table.name.lower(), col_lower,
                target_table.name.lower(), target_col.lower(),
            )
            if pair in explicit_pairs:
                continue

            rel = Relationship(
                source_schema=table.schema,
                source_table=table.name,
                source_column=col.name,
                target_schema=target_table.schema,
                target_table=target_table.name,
                target_column=target_col,
                type="inferred",
                cardinality=_infer_cardinality(table, col.name),
            )
            relationships.append(rel)
            logger.info(f"Inferred relationship: {table.name}.{col.name} -> {target_table.name}.{target_col}")

    return relationships


def _find_target_table(prefix: str, table_names: dict[str, TableMetadata]) -> TableMetadata | None:
    """Find a table matching the prefix with common plural forms."""
    candidates = [
        prefix,              # exact match: customer_id -> customer
        prefix + "s",        # simple plural: customer_id -> customers
        prefix + "es",       # es plural: address_id -> addresses
    ]

    # Handle ies plural: category_id -> categories
    if prefix.endswith("y"):
        candidates.append(prefix[:-1] + "ies")

    for candidate in candidates:
        if candidate in table_names:
            return table_names[candidate]

    return None


def _infer_cardinality(table: TableMetadata, column_name: str) -> str:
    """Infer relationship cardinality from indexes and table structure."""
    # Check if column has a unique index -> one-to-one
    for idx in table.indexes:
        cols = idx.get("column_names", [])
        if column_name in cols and idx.get("unique", False) and len(cols) == 1:
            return "one-to-one"

    # Check if this looks like a junction table (2 FK columns, both in PK)
    fk_columns = {fk.source_column for fk in table.foreign_keys}
    if len(fk_columns) == 2 and len(table.columns) <= 5:
        pk_set = set(table.primary_keys)
        if fk_columns.issubset(pk_set):
            return "many-to-many"

    return "one-to-many"
