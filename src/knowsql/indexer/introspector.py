"""SQLAlchemy-based schema introspection."""

import logging

from sqlalchemy import create_engine, inspect

from knowsql.indexer.models import DatabaseMetadata, TableMetadata, ColumnMetadata, ForeignKey

logger = logging.getLogger(__name__)


def introspect_database(connection_string: str) -> DatabaseMetadata:
    """Introspect a database and return its metadata."""
    engine = create_engine(connection_string)
    inspector = inspect(engine)
    dialect = engine.dialect.name

    # Get all schemas
    try:
        schemas = inspector.get_schema_names()
    except Exception:
        schemas = [None]

    # For SQLite, treat 'main' as None (default schema)
    if dialect == "sqlite":
        schemas = [None]

    tables = []

    for schema in schemas:
        # Skip internal schemas
        if schema in ("information_schema", "pg_catalog", "pg_toast"):
            continue

        # Get tables
        try:
            table_names = inspector.get_table_names(schema=schema)
        except Exception:
            table_names = []

        for table_name in table_names:
            table = _introspect_table(inspector, table_name, schema, dialect, is_view=False)
            if table:
                tables.append(table)

        # Get views
        try:
            view_names = inspector.get_view_names(schema=schema)
        except Exception:
            view_names = []

        for view_name in view_names:
            table = _introspect_table(inspector, view_name, schema, dialect, is_view=True)
            if table:
                tables.append(table)

    # Clean up schemas list
    clean_schemas = [s for s in schemas if s is not None]

    engine.dispose()

    return DatabaseMetadata(
        dialect=dialect,
        tables=tables,
        schemas=clean_schemas,
    )


def _introspect_table(inspector, table_name: str, schema: str | None, dialect: str, is_view: bool) -> TableMetadata | None:
    """Introspect a single table or view."""
    try:
        # Columns
        raw_columns = inspector.get_columns(table_name, schema=schema)
        columns = []
        for col in raw_columns:
            columns.append(ColumnMetadata(
                name=col["name"],
                type=str(col["type"]),
                nullable=col.get("nullable", True),
                is_primary_key=False,  # Set below from PK info
                default=str(col["default"]) if col.get("default") is not None else None,
                comment=col.get("comment"),
            ))

        # Primary keys
        if is_view:
            primary_keys = []
        else:
            try:
                pk_info = inspector.get_pk_constraint(table_name, schema=schema)
                primary_keys = pk_info.get("constrained_columns", []) if pk_info else []
            except Exception:
                primary_keys = []

        # Mark PK columns
        pk_set = set(primary_keys)
        for col in columns:
            if col.name in pk_set:
                col.is_primary_key = True

        # Foreign keys
        if is_view:
            foreign_keys = []
        else:
            try:
                raw_fks = inspector.get_foreign_keys(table_name, schema=schema)
                foreign_keys = []
                for fk in raw_fks:
                    for src_col, tgt_col in zip(fk["constrained_columns"], fk["referred_columns"]):
                        foreign_keys.append(ForeignKey(
                            source_column=src_col,
                            target_schema=fk.get("referred_schema"),
                            target_table=fk["referred_table"],
                            target_column=tgt_col,
                        ))
            except Exception:
                foreign_keys = []

        # Indexes
        if is_view:
            indexes = []
        else:
            try:
                indexes = inspector.get_indexes(table_name, schema=schema)
            except Exception:
                indexes = []

        # Table comment
        try:
            comment = inspector.get_table_comment(table_name, schema=schema).get("text")
        except Exception:
            comment = None

        return TableMetadata(
            name=table_name,
            schema=schema,
            is_view=is_view,
            columns=columns,
            primary_keys=primary_keys,
            foreign_keys=foreign_keys,
            indexes=indexes,
            comment=comment,
        )

    except Exception as e:
        logger.warning(f"Failed to introspect {schema}.{table_name}: {e}")
        return None
