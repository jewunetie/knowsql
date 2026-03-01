"""Data sampling and basic stats collection."""

import logging

from sqlalchemy import create_engine, MetaData, Table, select, func, cast, Float, text, case, literal_column
from sqlalchemy.exc import OperationalError

from knowsql.indexer.models import TableMetadata, TableSample, ColumnStats

logger = logging.getLogger(__name__)


def sample_tables(
    connection_string: str,
    tables: list[TableMetadata],
    sample_rows: int = 5,
    sample_mode: str = "full",
    max_columns_for_stats: int = 50,
    progress_callback=None,
) -> dict[str, TableSample]:
    """Sample data from all tables. Returns {table_name: TableSample}."""
    if sample_mode == "none":
        return {}

    engine = create_engine(connection_string)
    metadata = MetaData()
    results = {}

    for i, table_meta in enumerate(tables):
        try:
            sample = _sample_single_table(
                engine, metadata, table_meta,
                sample_rows=sample_rows,
                sample_mode=sample_mode,
                max_columns_for_stats=max_columns_for_stats,
            )
            results[table_meta.name] = sample
        except Exception as e:
            logger.warning(f"Failed to sample {table_meta.name}: {e}")
            results[table_meta.name] = TableSample(
                table_name=table_meta.name,
                row_count=0,
                sample_rows=[],
                column_stats={},
            )

        if progress_callback:
            progress_callback(i + 1, len(tables), table_meta.name)

    engine.dispose()
    return results


def _sample_single_table(
    engine,
    metadata: MetaData,
    table_meta: TableMetadata,
    sample_rows: int,
    sample_mode: str,
    max_columns_for_stats: int,
) -> TableSample:
    """Sample a single table with timeout."""
    schema = table_meta.schema
    sa_table = Table(table_meta.name, metadata, autoload_with=engine, schema=schema, extend_existing=True)

    with engine.connect() as conn:
        # Row count
        count_q = select(func.count()).select_from(sa_table)
        row_count = conn.execute(count_q).scalar() or 0

        # Update the table metadata with row count
        table_meta.row_count = row_count

        sample_data = []
        column_stats = {}

        if row_count == 0:
            return TableSample(
                table_name=table_meta.name,
                row_count=0,
                sample_rows=[],
                column_stats={},
            )

        # Sample rows (full mode only)
        if sample_mode == "full":
            sample_q = select(sa_table).limit(sample_rows)
            result = conn.execute(sample_q)
            col_names = list(result.keys())
            for row in result:
                sample_data.append({col_names[i]: _serialize_value(row[i]) for i in range(len(col_names))})

        # Column stats
        columns_to_stat = table_meta.columns[:max_columns_for_stats]
        if columns_to_stat:
            column_stats = _compute_column_stats(
                conn, sa_table, columns_to_stat, row_count,
                sample_mode=sample_mode,
            )

        return TableSample(
            table_name=table_meta.name,
            row_count=row_count,
            sample_rows=sample_data,
            column_stats=column_stats,
        )


def _compute_column_stats(conn, sa_table, columns, row_count, sample_mode="full"):
    """Compute stats for all columns in a single aggregation query."""
    stats = {}
    agg_exprs = []
    col_names = []

    for col_meta in columns:
        col = sa_table.c[col_meta.name]
        col_names.append(col_meta.name)

        # COUNT(DISTINCT col)
        agg_exprs.append(func.count(func.distinct(col)).label(f"{col_meta.name}__distinct"))

        # Null rate: SUM(CASE WHEN col IS NULL THEN 1 ELSE 0 END) / COUNT(*)
        null_sum = func.sum(case((col.is_(None), 1), else_=0))
        agg_exprs.append(
            cast(null_sum, Float) / cast(func.count(), Float)
        )

    if not agg_exprs:
        return stats

    try:
        agg_q = select(*agg_exprs).select_from(sa_table)
        result = conn.execute(agg_q)
        row = result.fetchone()

        if row:
            for i, col_name in enumerate(col_names):
                distinct_count = row[i * 2] or 0
                null_rate = round(float(row[i * 2 + 1] or 0) * 100, 2)

                sample_values = []
                enum_values = None

                # Low cardinality enum detection (full mode only)
                if sample_mode == "full" and 0 < distinct_count < 20:
                    try:
                        col = sa_table.c[col_name]
                        distinct_q = select(func.distinct(col)).select_from(sa_table).limit(20)
                        distinct_result = conn.execute(distinct_q)
                        enum_values = [_serialize_value(r[0]) for r in distinct_result if r[0] is not None]
                    except Exception:
                        pass

                # Sample values (full mode only)
                if sample_mode == "full" and not enum_values:
                    try:
                        col = sa_table.c[col_name]
                        sample_q = select(func.distinct(col)).select_from(sa_table).limit(10)
                        sample_result = conn.execute(sample_q)
                        sample_values = [_serialize_value(r[0]) for r in sample_result if r[0] is not None]
                    except Exception:
                        pass

                stats[col_name] = ColumnStats(
                    distinct_count=distinct_count,
                    null_rate=null_rate,
                    sample_values=sample_values,
                    enum_values=enum_values,
                )
    except Exception as e:
        logger.warning(f"Failed to compute aggregated stats: {e}")
        # Fallback: basic stats per column
        for col_name in col_names:
            stats[col_name] = ColumnStats(distinct_count=0, null_rate=0.0)

    return stats


def _serialize_value(val) -> str:
    """Serialize a value to string for display."""
    if val is None:
        return "NULL"
    return str(val)
