"""Data models for the indexing pipeline."""

from dataclasses import dataclass, field


@dataclass
class ColumnMetadata:
    name: str
    type: str
    nullable: bool
    is_primary_key: bool
    default: str | None = None
    comment: str | None = None


@dataclass
class ForeignKey:
    source_column: str
    target_schema: str | None
    target_table: str
    target_column: str


@dataclass
class TableMetadata:
    name: str
    schema: str | None
    is_view: bool
    columns: list[ColumnMetadata]
    primary_keys: list[str]
    foreign_keys: list[ForeignKey]
    indexes: list[dict]
    comment: str | None
    row_count: int | None = None


@dataclass
class DatabaseMetadata:
    dialect: str
    tables: list[TableMetadata]
    schemas: list[str] = field(default_factory=list)


@dataclass
class ColumnStats:
    distinct_count: int
    null_rate: float
    sample_values: list[str] = field(default_factory=list)
    enum_values: list[str] | None = None


@dataclass
class TableSample:
    table_name: str
    row_count: int
    sample_rows: list[dict] = field(default_factory=list)
    column_stats: dict[str, ColumnStats] = field(default_factory=dict)


@dataclass
class Relationship:
    source_schema: str | None
    source_table: str
    source_column: str
    target_schema: str | None
    target_table: str
    target_column: str
    type: str  # "explicit_fk" or "inferred"
    cardinality: str | None = None  # "one-to-many", "one-to-one", "many-to-many"


@dataclass
class DomainCluster:
    name: str
    description: str
    tables: list[str]
    also_relevant_to: dict[str, list[str]] = field(default_factory=dict)
