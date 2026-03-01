"""Generate the file hierarchy and markdown documentation."""

import logging
import os
import re
from pathlib import Path

from knowsql.indexer.models import (
    DatabaseMetadata, TableMetadata, TableSample, Relationship, DomainCluster, ColumnStats,
)
from knowsql.llm.provider import LLMMessage

logger = logging.getLogger(__name__)

TOKEN_WARNING_THRESHOLD = 8000


def generate_index(
    output_dir: str,
    db_metadata: DatabaseMetadata,
    samples: dict[str, TableSample],
    relationships: list[Relationship],
    domains: list[DomainCluster],
    llm,
    progress_callback=None,
) -> dict:
    """Generate the full file hierarchy. Returns summary stats."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / "domains").mkdir(exist_ok=True)
    (root / "cross_references").mkdir(exist_ok=True)

    # Write metadata file for dialect and schema info
    import json
    meta = {
        "dialect": db_metadata.dialect,
        "schemas": db_metadata.schemas,
        "table_count": len(db_metadata.tables),
    }
    (root / "META.json").write_text(json.dumps(meta, indent=2))

    # Build lookups
    table_map = {t.name: t for t in db_metadata.tables}
    sample_map = samples
    table_to_domain = {}
    for domain in domains:
        for table_name in domain.tables:
            table_to_domain[table_name] = domain.name

    multi_schema = len(db_metadata.schemas) > 1
    total_steps = 1 + len(domains) + len(db_metadata.tables) + 2  # INDEX + domains + tables + RELS + GLOSSARY
    step = 0

    def update_progress(description):
        nonlocal step
        step += 1
        if progress_callback:
            progress_callback(step, total_steps, description)

    # INDEX.md
    update_progress("Generating INDEX.md")
    index_content = _generate_index_md(db_metadata, domains, llm)
    _write_file(root / "INDEX.md", index_content)

    # DOMAIN.md for each domain
    for domain in domains:
        update_progress(f"Generating {domain.name}/DOMAIN.md")
        domain_dir = root / "domains" / _sanitize(domain.name)
        domain_dir.mkdir(parents=True, exist_ok=True)
        (domain_dir / "tables").mkdir(exist_ok=True)

        domain_tables = [table_map[t] for t in domain.tables if t in table_map]
        domain_rels = _get_domain_relationships(domain.name, domain.tables, relationships, table_to_domain)

        domain_content = _generate_domain_md(
            domain, domain_tables, domain_rels, sample_map, table_to_domain, llm,
        )
        _write_file(domain_dir / "DOMAIN.md", domain_content)

    # Table .md files
    for table in db_metadata.tables:
        domain_name = table_to_domain.get(table.name, "uncategorized")
        update_progress(f"Generating {table.name}.md")

        domain_dir = root / "domains" / _sanitize(domain_name) / "tables"
        domain_dir.mkdir(parents=True, exist_ok=True)

        filename = _get_table_filename(table, multi_schema)
        sample = sample_map.get(table.name)
        table_rels = [r for r in relationships
                      if r.source_table == table.name or r.target_table == table.name]

        table_content = _generate_table_md(table, sample, table_rels, domain_name, llm)
        _write_file(domain_dir / filename, table_content)

        # Split wide tables
        if len(table.columns) > 80:
            detail_filename = filename.replace(".md", "_columns_detail.md")
            detail_content = _generate_columns_detail(table, sample, llm)
            _write_file(domain_dir / detail_filename, detail_content)

    # RELATIONSHIPS.md
    update_progress("Generating RELATIONSHIPS.md")
    rels_content = _generate_relationships_md(relationships, table_to_domain, llm)
    _write_file(root / "cross_references" / "RELATIONSHIPS.md", rels_content)

    # GLOSSARY.md
    update_progress("Generating GLOSSARY.md")
    glossary_content = _generate_glossary_md(db_metadata, samples, llm)
    _write_file(root / "cross_references" / "GLOSSARY.md", glossary_content)

    return {
        "table_count": len(db_metadata.tables),
        "domain_count": len(domains),
        "file_count": step,
    }


def _generate_index_md(db_metadata, domains, llm) -> str:
    domain_lines = []
    for d in domains:
        domain_lines.append(f"- {d.name} ({len(d.tables)} tables): {d.description}")

    prompt = f"""You are generating the top-level index file for a database schema documentation.
This file will be read by an AI agent that needs to navigate the schema to find
relevant tables for a user's query. The file should help the agent quickly decide
which domain(s) to explore.

Database type: {db_metadata.dialect}
Total tables: {len(db_metadata.tables)}

Domains:
{chr(10).join(domain_lines)}

Generate a markdown file with:
1. A one-paragraph database overview
2. A domains section listing each domain with table count, description, and
   3-5 keywords/synonyms for the domain (e.g., for "orders" domain: purchases,
   transactions, sales, buying)
3. A "Common Question Patterns" section that maps question types to starting domains
   (e.g., "Revenue questions -> start with finance/, may need orders/")
4. A note that cross_references/AMBIGUOUS_TERMS.md should be checked when a
   user's question contains terms that could refer to multiple tables

Keep it concise. The entire file should be 300-500 words maximum.
Do not use contractions."""

    messages = [LLMMessage(role="user", content=prompt)]
    response = llm.complete(messages)
    return response.content


def _generate_domain_md(domain, tables, domain_rels, sample_map, table_to_domain, llm) -> str:
    table_lines = []
    for t in tables:
        sample = sample_map.get(t.name)
        row_count = sample.row_count if sample else (t.row_count or "?")
        col_names = ", ".join(c.name for c in t.columns)
        table_lines.append(f"- {t.name} ({row_count} rows): columns are {col_names}")

    within_rels = []
    cross_rels = []
    domain_table_set = set(domain.tables)
    for r in domain_rels:
        line = f"- {r.source_table}.{r.source_column} -> {r.target_table}.{r.target_column} ({r.type}, {r.cardinality or 'unknown'})"
        if r.source_table in domain_table_set and r.target_table in domain_table_set:
            within_rels.append(line)
        else:
            cross_rels.append(line)

    cross_domain_notes = []
    for table_name, other_domains in domain.also_relevant_to.items():
        cross_domain_notes.append(f"- {table_name} is also relevant to: {', '.join(other_domains)}")

    prompt = f"""You are generating a domain summary file for the "{domain.name}" domain in a
database schema documentation. This file will be read by an AI agent navigating
the schema. It should help the agent decide which specific table files to read.

Domain: {domain.name}
Description: {domain.description}

Tables in this domain:
{chr(10).join(table_lines)}

Relationships within this domain:
{chr(10).join(within_rels) if within_rels else "(none)"}

Cross-domain relationships:
{chr(10).join(cross_rels) if cross_rels else "(none)"}

Conceptual cross-domain relevance:
{chr(10).join(cross_domain_notes) if cross_domain_notes else "(none)"}

Generate a markdown file with:
1. A one-paragraph description of what this domain covers
2. Domain-level keywords: alternative terms or synonyms a user might use to
   refer to this domain's subject area
3. A table list with a one-line summary of each table's purpose, plus 3-5
   keywords per table that a user might search for
4. A relationships section showing how tables connect within the domain
5. A cross-domain relationships section showing connections to other domains
6. A "When to use this domain" section with example question patterns

Keep it concise. Each table summary should be one line.
Do not use contractions."""

    messages = [LLMMessage(role="user", content=prompt)]
    response = llm.complete(messages)
    return response.content


def _generate_table_md(table, sample, table_rels, domain_name, llm) -> str:
    # Build column info
    col_lines = []
    for col in table.columns:
        line = f"- {col.name} ({col.type}, {'nullable' if col.nullable else 'not null'}"
        if col.is_primary_key:
            line += ", PK"
        if col.default:
            line += f", default: {col.default}"
        line += ")"

        if sample and col.name in sample.column_stats:
            stats = sample.column_stats[col.name]
            line += f"\n  Stats: {stats.distinct_count} distinct values, {stats.null_rate}% null"
            if stats.enum_values:
                line += f"\n  Known values: {', '.join(stats.enum_values[:20])}"
            elif stats.sample_values:
                line += f"\n  Sample values: {', '.join(stats.sample_values[:10])}"
        if col.comment:
            line += f"\n  DB comment: {col.comment}"
        col_lines.append(line)

    # Sample rows
    sample_text = "(no sample data)"
    if sample and sample.sample_rows:
        rows = sample.sample_rows[:5]
        if rows:
            headers = list(rows[0].keys())[:10]  # Limit columns for readability
            sample_text = " | ".join(headers) + "\n"
            sample_text += " | ".join(["---"] * len(headers)) + "\n"
            for row in rows:
                sample_text += " | ".join(str(row.get(h, "")) for h in headers) + "\n"

    # Relationships
    rel_lines = []
    for r in table_rels:
        if r.source_table == table.name:
            rel_lines.append(f"- {table.name}.{r.source_column} -> {r.target_table}.{r.target_column} ({r.type}, {r.cardinality or 'unknown'})")
        else:
            rel_lines.append(f"- {r.source_table}.{r.source_column} -> {table.name}.{r.target_column} ({r.type}, {r.cardinality or 'unknown'})")

    row_count = sample.row_count if sample else (table.row_count or "unknown")
    view_note = " (VIEW)" if table.is_view else ""

    prompt = f"""You are generating a detailed table documentation file for the "{table.name}" table{view_note}.
This file will be read by an AI agent that is deciding whether to use this table in
a SQL query. The file should give the agent everything it needs to understand what
this table contains and how to use it.

Table: {table.name}{view_note}
Schema: {table.schema or 'default'}
Row count: {row_count}

Columns:
{chr(10).join(col_lines)}

Sample rows (first {len(sample.sample_rows) if sample and sample.sample_rows else 0}):
{sample_text}

Relationships:
{chr(10).join(rel_lines) if rel_lines else "(none)"}

Generate a markdown file with these exact sections:

# {table.name}
A 1-2 sentence description of what this table contains and represents.

## Keywords
A comma-separated list of alternative terms, synonyms, and related business
concepts that a user might use when they mean this table.
Format as a single line: "Keywords: term1, term2, term3, ..."
For each column, also include column-level keywords inline in the Columns section.

## Columns
For each column:
- Name, type, constraints
- A human-readable description of what the column contains
- Keywords: alternative terms a user might use for this column
- Notable characteristics (always null, low cardinality, enum-like, etc.)

## Sample Values
A small readable table showing 3-5 sample rows with the most informative columns.

## Relationships
List each relationship with a brief explanation of what it means.

## Use This Table When...
Bullet points describing the scenarios where this table is the right choice.

## Do Not Use This Table When...
Bullet points describing common misconceptions or cases where a different table
would be more appropriate (if you can infer any).

Do not use contractions.
Keep descriptions factual -- only describe what you can infer from the metadata
and sample data. Do not speculate about business logic you cannot verify."""

    messages = [LLMMessage(role="user", content=prompt)]
    response = llm.complete(messages)
    return response.content


def _generate_columns_detail(table, sample, llm) -> str:
    """Generate detailed column documentation for wide tables."""
    col_lines = []
    for col in table.columns:
        line = f"### {col.name}\n- Type: {col.type}\n- Nullable: {col.nullable}"
        if col.is_primary_key:
            line += "\n- Primary Key"
        if sample and col.name in sample.column_stats:
            stats = sample.column_stats[col.name]
            line += f"\n- Distinct values: {stats.distinct_count}"
            line += f"\n- Null rate: {stats.null_rate}%"
            if stats.enum_values:
                line += f"\n- Known values: {', '.join(stats.enum_values)}"
        col_lines.append(line)

    return f"# {table.name} - Column Details\n\n" + "\n\n".join(col_lines)


def _generate_relationships_md(relationships, table_to_domain, llm) -> str:
    if not relationships:
        return "# Relationships\n\nNo relationships detected."

    # Group by domain pair
    rel_lines = []
    for r in relationships:
        src_domain = table_to_domain.get(r.source_table, "unknown")
        tgt_domain = table_to_domain.get(r.target_table, "unknown")
        rel_lines.append(
            f"- {r.source_table}.{r.source_column} -> {r.target_table}.{r.target_column} "
            f"({r.type}, {r.cardinality or 'unknown'}) "
            f"[{src_domain} -> {tgt_domain}]"
        )

    # Batch if too many
    if len(rel_lines) > 300:
        # Process in batches
        batches = [rel_lines[i:i + 150] for i in range(0, len(rel_lines), 150)]
        parts = []
        for batch in batches:
            parts.append(_generate_relationships_batch(batch, llm))
        return "\n\n".join(parts)

    prompt = f"""Generate a RELATIONSHIPS.md file that helps an AI agent understand how tables connect.

All relationships in this database:
{chr(10).join(rel_lines)}

Generate a markdown file with:
1. A summary of the relationship structure
2. Relationships organized by domain pair
3. Join path guidance for common multi-hop queries (e.g., "To connect customers to products, go through orders: customers -> orders -> order_items -> products")

Focus on practical join guidance. Do not use contractions."""

    messages = [LLMMessage(role="user", content=prompt)]
    response = llm.complete(messages)
    return response.content


def _generate_relationships_batch(rel_lines, llm) -> str:
    prompt = f"""Generate join path guidance for these relationships:

{chr(10).join(rel_lines)}

Focus on practical join paths. Do not use contractions."""

    messages = [LLMMessage(role="user", content=prompt)]
    response = llm.complete(messages)
    return response.content


def _generate_glossary_md(db_metadata, samples, llm) -> str:
    # Collect all table names, column names, and enum values
    entries = []
    for table in db_metadata.tables:
        col_names = ", ".join(c.name for c in table.columns)
        entries.append(f"- Table: {table.name} (columns: {col_names})")

        sample = samples.get(table.name)
        if sample:
            for col_name, stats in sample.column_stats.items():
                if stats.enum_values:
                    entries.append(f"  - {table.name}.{col_name} values: {', '.join(stats.enum_values)}")

    # Batch for large DBs
    if len(db_metadata.tables) > 200:
        # Split into batches
        batch_size = 100
        batches = [entries[i:i + batch_size * 3] for i in range(0, len(entries), batch_size * 3)]
        parts = []
        for batch in batches:
            parts.append(_generate_glossary_batch(batch, llm))
        return "# Glossary\n\n> Note: These mappings are inferred and may need human curation.\n\n" + "\n\n".join(parts)

    prompt = f"""Generate a GLOSSARY.md file that maps business concepts to database tables/columns.

Database schema:
{chr(10).join(entries)}

Generate a glossary mapping likely business concepts to the physical tables/columns that represent them. For example:
- "customer" -> customers table
- "revenue" -> orders.total_amount
- "churn" -> customers.is_active = 0

Include a note at the top saying these mappings are inferred and may need human curation.
Do not use contractions."""

    messages = [LLMMessage(role="user", content=prompt)]
    response = llm.complete(messages)
    return response.content


def _generate_glossary_batch(entries, llm) -> str:
    prompt = f"""Generate glossary entries for these schema elements:

{chr(10).join(entries)}

Map business concepts to tables/columns. Do not use contractions."""

    messages = [LLMMessage(role="user", content=prompt)]
    response = llm.complete(messages)
    return response.content


def _get_domain_relationships(domain_name, domain_tables, all_relationships, table_to_domain):
    """Get relationships involving tables in this domain."""
    domain_set = set(domain_tables)
    rels = []
    for r in all_relationships:
        if r.source_table in domain_set or r.target_table in domain_set:
            rels.append(r)
    return rels


def _get_table_filename(table: TableMetadata, multi_schema: bool) -> str:
    if multi_schema and table.schema:
        name = f"{table.schema}__{table.name}"
    else:
        name = table.name
    return _sanitize(name) + ".md"


def _sanitize(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


def _write_file(path: Path, content: str):
    """Write content to file with token size warning."""
    path.write_text(content)
    estimated_tokens = len(content) // 4
    if estimated_tokens > TOKEN_WARNING_THRESHOLD:
        logger.warning(f"File {path} is ~{estimated_tokens} tokens (>{TOKEN_WARNING_THRESHOLD})")
