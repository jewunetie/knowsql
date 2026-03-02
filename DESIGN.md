# KnowSQL: SQL Schema Discovery Agent -- Design Document

## Overview

A CLI tool that solves the "which tables should I query?" problem for any SQL database. It works in two phases:

1. **Indexing** -- Connects to a database, introspects the schema, samples data, and uses an LLM to generate a navigable file system index with human-readable descriptions of every table, column, relationship, and business concept.
2. **Query-time agent** -- Takes a natural language question, navigates the index using progressive disclosure (reading only what it needs, like a human DBA would), identifies the right tables/columns/joins, and generates the SQL.

The key insight: existing text-to-SQL tools (like Uber's QueryGPT) fail at table discovery because they search raw DDL with semantic similarity, which does not work -- natural language and `CREATE TABLE` statements live in different embedding spaces. This tool bridges the gap by generating a natural language semantic layer that an LLM agent can reason over.

No vector databases. No RAG. The agent navigates a file hierarchy, reading progressively deeper as needed.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   CLI Interface                 │
│  Commands: index, query, repl                   │
└─────────────┬───────────────────┬───────────────┘
              │                   │
              v                   v
┌─────────────────────┐ ┌─────────────────────────┐
│   Indexing Pipeline │ │   Query-Time Agent      │
│                     │ │                         │
│  1. Introspect      │ │  1. Read INDEX.md       │
│  2. Sample data     │ │  2. Read DOMAIN.md(s)   │
│  3. Infer relations │ │  3. Read table files    │
│  4. Cluster domains │ │  4. Check relationships │
│  5. Generate index  │ │  5. Check ambiguous     │
│  6. Detect keyword  │ │  6. Propose tables      │
│     conflicts       │ │  7. Generate SQL        │
└──────────┬──────────┘ └────────────┬────────────┘
           │                         │
           v                         v
┌─────────────────────┐ ┌─────────────────────────┐
│   SQLAlchemy        │ │   LLM Provider          │
│   (any SQL DB)      │ │   (Claude or OpenAI)    │
└─────────────────────┘ └─────────────────────────┘
```

## Project Structure

```
sql-schema-agent/
  pyproject.toml
  README.md
  src/
    sql_schema_agent/
      __init__.py
      cli.py                    # Click-based CLI entry point
      config.py                 # Configuration management

      indexer/
        __init__.py
        introspector.py         # SQLAlchemy-based schema introspection
        sampler.py              # Data sampling and basic stats
        relationship_detector.py # FK + implicit relationship detection
        domain_clusterer.py     # LLM-based domain clustering
        index_generator.py      # Generates the file system index
        keyword_conflict_detector.py # Parses keywords from generated files, detects conflicts
        pipeline.py             # Orchestrates the full indexing pipeline

      agent/
        __init__.py
        navigator.py            # File system navigation logic
        table_selector.py       # Table/column selection reasoning
        sql_generator.py        # SQL generation from selected tables
        agent.py                # Main agent loop orchestrating navigation + generation

      llm/
        __init__.py
        provider.py             # Abstract LLM interface
        anthropic_provider.py   # Claude implementation
        openai_provider.py      # OpenAI implementation

      utils/
        __init__.py
        display.py              # Rich console output formatting
```

## Configuration

Configuration via a YAML file (`~/.sql-schema-agent/config.yaml`) or environment variables, with CLI flags as overrides.

```yaml
llm:
  provider: "anthropic"                    # "anthropic" or "openai"
  model: "claude-sonnet-4-20250514"        # Model identifier (OpenAI default: "gpt-5-mini")
  api_key_env: "ANTHROPIC_API_KEY"         # Env var name containing the API key

indexer:
  sample_rows: 5                           # Number of sample rows per table
  sample_mode: "full"                      # "full" (rows + stats), "schema-only" (aggregates only), "none" (no sampling)
  max_columns_for_stats: 50                # Skip detailed stats for very wide tables
  output_dir: "./schema_index"             # Where to write the index

agent:
  max_navigation_steps: 20                 # Safety limit on file reads per query
  confirm_tables: true                     # Ask user to confirm table selection before SQL gen

indexer_advanced:
  keyword_stopwords_extend: []             # Additional stopwords to add to the default list
  keyword_stopwords_override: null         # If set, replaces the default stopword list entirely
```

Environment variable overrides follow the pattern `SQL_SCHEMA_AGENT_LLM_PROVIDER`, `SQL_SCHEMA_AGENT_LLM_MODEL`, etc.

## CLI Interface

Built with Click.

```bash
# Index a database
sql-schema-agent index \
  --connection-string "postgresql://user:pass@localhost/mydb" \
  --output-dir ./schema_index \
  --provider anthropic \
  --model claude-sonnet-4-20250514

# One-shot query
sql-schema-agent query \
  --index-dir ./schema_index \
  --connection-string "postgresql://user:pass@localhost/mydb" \
  --question "How many customers signed up last month by region?"

# Interactive REPL
sql-schema-agent repl \
  --index-dir ./schema_index \
  --connection-string "postgresql://user:pass@localhost/mydb"
```

### `index` command

Required: `--connection-string`
Optional: `--output-dir` (default: `./schema_index`), `--provider`, `--model`, `--yes` (skip interactive confirmations), `--no-sample-data` (skip all data sampling -- no row data sent to LLM), `--sample-schema-only` (run aggregate stats only -- no actual row values sent to LLM)

Behavior:
- Connects to the database via SQLAlchemy
- Runs the full indexing pipeline
- Writes the file system index to disk
- Prints a summary (table count, domain count, time taken, estimated token cost)

Progress output via Rich: show which step is running, which tables are being processed, etc.

### `query` command

Required: `--question`
Optional: `--index-dir` (default: `./schema_index`, matching the indexer default), `--connection-string` (needed only if you want to execute the generated SQL), `--provider`, `--model`, `--execute` (flag to actually run the query and show results), `--show-navigation` (flag to show the agent's file reads for debugging/transparency)

Behavior:
- Loads the index from disk
- Runs the agent to navigate the index and find relevant tables
- If `confirm_tables` is enabled, shows the proposed tables and asks for confirmation
- Generates SQL
- If `--execute` is set and `--connection-string` is provided, runs the query and displays results
- Always shows: selected tables with reasoning, the generated SQL, and an explanation

### `repl` command

Required: (none -- all have defaults)
Optional: `--index-dir` (default: `./schema_index`), `--connection-string`, `--provider`, `--model`

Behavior:
- Enters an interactive loop
- User types natural language questions
- Agent navigates, selects tables, generates SQL
- If connection string is provided, offers to execute
- Maintains conversation context: keep prior question/answer pairs in the agent's message history so follow-up questions work naturally (e.g., "now break that down by month" or "use a different date range"). Reset context with a `/clear` command.
- Special commands: `/tables` (list all tables), `/domains` (list domains), `/inspect <table>` (show table details), `/clear` (reset conversation context), `/exit`

## Indexing Pipeline

### Step 1: Introspection (`introspector.py`)

Uses SQLAlchemy's `inspect()` to extract:
- All table names and schemas (via `inspector.get_table_names()`)
- All view names and schemas (via `inspector.get_view_names()`) -- views are treated as first-class objects in the index alongside tables, but flagged as views
- Column names, types, nullability, defaults
- Primary keys
- Foreign key constraints (source column, target table, target column)
- Indexes
- Table comments and column comments (if the database supports them)

**View-specific handling:** Views typically lack explicit primary keys and foreign keys in the database metadata catalog. For views:
- Set `primary_keys` to an empty list
- Set `foreign_keys` to an empty list
- Rely on the implicit relationship detection in Step 3 to infer relationships based on column naming patterns
- Add a `is_view: bool` field to `TableMetadata` so downstream steps can note this in the generated documentation (the agent should know a table is a view, as it affects performance expectations and mutability)

Also capture the database dialect (`engine.dialect.name`) and store it for use in INDEX.md generation and SQL generation (dialect-specific syntax).

Output: a `DatabaseMetadata` wrapper containing the dialect and a list of `TableMetadata` dataclass objects.

```python
@dataclass
class DatabaseMetadata:
    dialect: str                  # e.g., "postgresql", "mysql", "sqlite"
    tables: list[TableMetadata]
    schemas: list[str]            # All schemas found in the database

@dataclass
class ColumnMetadata:
    name: str
    type: str                    # SQLAlchemy type as string, e.g., "VARCHAR(255)"
    nullable: bool
    is_primary_key: bool
    default: str | None
    comment: str | None

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
    is_view: bool                 # True for views, False for base tables
    columns: list[ColumnMetadata]
    primary_keys: list[str]
    foreign_keys: list[ForeignKey]
    indexes: list[dict]
    comment: str | None
    row_count: int | None        # Filled in by sampler
```

### Step 2: Data Sampling (`sampler.py`)

For each table:
- Use SQLAlchemy query objects (not raw SQL strings) to handle dialect differences automatically. Specifically, use `select(table).limit(sample_rows)` for sampling and `select(func.count()).select_from(table)` for row count. This avoids `LIMIT` vs `TOP` vs `ROWNUM` dialect issues.
- For column stats, run a single aggregation query per table that computes all column stats at once (rather than one query per column). The query should compute, for each column (up to `max_columns_for_stats` columns):
  - `COUNT(DISTINCT column)` for cardinality
  - Null rate via `SUM(CASE WHEN column IS NULL THEN 1 ELSE 0 END)` divided by `COUNT(*)`, cast to float in a dialect-appropriate way (PostgreSQL: `::float`, MySQL: `* 1.0`, SQLite: `CAST(... AS REAL)`) -- or better, use SQLAlchemy's `cast(... , Float)` to handle this generically
  - For string/categorical columns with low cardinality (< 20 distinct values): a separate `SELECT DISTINCT column FROM {schema}.{table_name}` to enumerate all values
- All queries must be schema-qualified. Use SQLAlchemy's `Table` objects with explicit `schema` parameter to ensure this.

Output: a `TableSample` dataclass per table.

```python
@dataclass
class ColumnStats:
    distinct_count: int
    null_rate: float
    sample_values: list[str]      # Up to 10 representative values
    enum_values: list[str] | None # All values if cardinality < 20

@dataclass
class TableSample:
    table_name: str
    row_count: int
    sample_rows: list[dict]       # List of {column: value} dicts
    column_stats: dict[str, ColumnStats]
```

Use error handling per table -- if a table cannot be sampled (permissions, views that fail to materialize, row-level security, or extremely long-running queries), log a warning and continue with whatever metadata is available from introspection alone. Set a per-table query timeout (default 10 seconds) to avoid blocking on large or complex views. Tables that fail sampling should still get index files, but their documentation will note that sample data was unavailable.

**Data privacy warning:** Sample rows are sent to the LLM provider (Anthropic or OpenAI) during indexing to help generate accurate column descriptions. This means literal row data -- including any PII, PHI, financial records, or other sensitive values -- will leave the database and enter a third-party API. The CLI must:
1. Display a prominent warning before sampling begins: "WARNING: This tool will send sample row data from your database to {provider}. If your database contains PII, PHI, financial data, or other sensitive information, consider using --no-sample-data to skip row sampling (descriptions will be less accurate but no row data will leave your network)."
2. Require the user to confirm with `--yes` or an interactive `[y/N]` prompt.
3. Support a `--no-sample-data` flag that skips Step 2 entirely. When this flag is set, table .md files are generated from schema metadata only (column names, types, constraints, comments) without sample values or enum value enumeration. Descriptions will be less precise but no actual data leaves the database.
4. Support a `--sample-schema-only` flag as a middle ground: run `COUNT(*)`, `COUNT(DISTINCT col)`, and null rate queries (which return only aggregates, not row data) but skip `SELECT * LIMIT N` and `SELECT DISTINCT col` (which return actual values).

### Step 3: Relationship Detection (`relationship_detector.py`)

Two sources of relationships:

**Explicit:** Foreign keys from Step 1. These are definitive.

**Implicit:** Heuristic detection for databases without FK constraints:
- Naming convention matching: if a column named `{X}_id` exists in `table_a`, look for a table named `{X}` (or common plurals: `{X}s`, `{X}es`, `{X}ies`) that has a primary key column (typically `id` or `{X}_id`), and infer a relationship from `table_a.{X}_id` to that table's PK.
- Shared column matching: if `table_a.user_id` and `table_b.user_id` both exist and neither table is the "source" table (i.e., neither is named `user` or `users`), note this as a potential shared-dimension relationship but mark it lower confidence.
- Do NOT infer relationships for generic column names like `id`, `name`, `type`, `status`, `created_at`, `updated_at`, etc.

Output: a list of `Relationship` objects.

```python
@dataclass
class Relationship:
    source_schema: str | None
    source_table: str
    source_column: str
    target_schema: str | None
    target_table: str
    target_column: str
    type: str                     # "explicit_fk" or "inferred"
    cardinality: str | None       # "one-to-many", "one-to-one", "many-to-many"
```

### Step 4: Domain Clustering (`domain_clusterer.py`)

Send all table names, their column names, and their one-line comments (if available) to the LLM. Ask it to cluster the tables into business domains. Domains must be MECE (Mutually Exclusive, Collectively Exhaustive): every table belongs to exactly one domain, and no table is left unassigned.

Prompt structure:

```
You are analyzing a database schema to organize tables into business domains.

Here are all the tables in the database with their columns:

{for each table}
- {table_name}: {comma-separated column names}
{end for}

Group these tables into logical business domains. Each domain should represent
a coherent area of the business or application (e.g., "customers", "orders",
"inventory", "authentication").

Rules:
- Domains must be MECE (Mutually Exclusive, Collectively Exhaustive):
  - Every table in the list above must appear in exactly one domain (no omissions)
  - No table may appear in more than one domain
- Aim for 3-15 domains depending on database size
- Use lowercase, single-word or hyphenated domain names
- If a table could reasonably belong to multiple domains, assign it to the domain
  where it is most likely to be queried, and note the cross-domain relevance in
  the "also_relevant_to" field

Respond in JSON:
{
  "domains": {
    "domain_name": {
      "description": "One sentence describing what this domain covers",
      "tables": ["table1", "table2"],
      "also_relevant_to": {"table1": ["other-domain"]}
    }
  }
}
```

**Post-LLM validation (programmatic, not LLM-based):**

After receiving the clustering response, run these checks:
1. **Exhaustive check:** Diff the set of tables in the response against the full table list from introspection. Any missing tables should be flagged and re-assigned in a follow-up LLM call that asks specifically where those tables belong.
2. **Exclusive check:** Check for tables appearing in more than one domain. If found, deduplicate by keeping only the first assignment and logging a warning.
3. **Empty domain check:** Remove any domains with zero tables.

Output: a dict mapping domain name to list of table names + domain description + cross-domain relevance notes.

**Large database batching:** If the database has more than 200 tables, the full table list may exceed context limits. In that case, split tables into batches of ~100, cluster each batch independently, then do a final merge pass where the LLM sees all proposed domain names and reassigns/consolidates as needed. Run the MECE validation after the final merge.

### Step 5: Index Generation (`index_generator.py`)

Generate the file hierarchy and all markdown files. This step makes multiple LLM calls.

#### File structure generated:

```
{output_dir}/
  INDEX.md
  domains/
    {domain_name}/
      DOMAIN.md
      tables/
        {table_name}.md
  cross_references/
    RELATIONSHIPS.md
    GLOSSARY.md
    AMBIGUOUS_TERMS.md
```

#### File naming convention

Table files use the pattern `{schema}__{table_name}.md` (double underscore separator). If there is only one schema (common case), omit the schema prefix and just use `{table_name}.md`. Sanitize filenames: replace any characters not in `[a-zA-Z0-9_-]` with underscores.

#### File size guardrails

To prevent any single file from overwhelming the agent's context window during query-time navigation:

- **Table `.md` files:** If a table has more than 80 columns, split the Columns section into a summary (all columns listed with name and type on one line each, no descriptions) in the main file, and a separate `{table_name}_columns_detail.md` file in the same directory with full descriptions and keywords. The main file should reference the detail file with a note like "For full column descriptions, see {table_name}_columns_detail.md". The agent can then use `read_file` with the `section` parameter or read the detail file only when needed.
- **`DOMAIN.md` files:** If a domain has more than 40 tables, split into a summary listing (table name + one-line description + keywords) and group tables into sub-sections by functional area. The summary should always fit within approximately 4,000 tokens.
- **Soft limit warning:** If any generated file exceeds 8,000 tokens (estimated via `len(text) / 4`), log a warning during indexing. This is for visibility, not a hard failure.

#### INDEX.md generation

One LLM call. Provide: domain names, domain descriptions, table counts per domain, total table count, database type.

Prompt:

```
You are generating the top-level index file for a database schema documentation.
This file will be read by an AI agent that needs to navigate the schema to find
relevant tables for a user's query. The file should help the agent quickly decide
which domain(s) to explore.

Database type: {dialect, e.g., "PostgreSQL"}
Total tables: {count}

Domains:
{for each domain}
- {domain_name} ({table_count} tables): {domain_description}
{end for}

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
Do not use contractions.
```

#### DOMAIN.md generation

One LLM call per domain. Provide: domain name, domain description, list of tables with their column names and row counts, relationships between tables in this domain, cross-domain relationships, and any "also relevant to" notes from domain clustering (tables that conceptually relate to other domains even without FK relationships).

Prompt:

```
You are generating a domain summary file for the "{domain_name}" domain in a
database schema documentation. This file will be read by an AI agent navigating
the schema. It should help the agent decide which specific table files to read.

Domain: {domain_name}
Description: {domain_description}

Tables in this domain:
{for each table}
- {table_name} ({row_count} rows): columns are {comma-separated column names}
{end for}

Relationships within this domain:
{list of relationships between tables in this domain}

Cross-domain relationships:
{list of relationships to tables in other domains}

Conceptual cross-domain relevance:
{tables in this domain that are also relevant to other domains, from clustering}
{e.g., "customer_orders is in this domain but also relevant to the 'customers' domain"}

Generate a markdown file with:
1. A one-paragraph description of what this domain covers
2. Domain-level keywords: alternative terms or synonyms a user might use to
   refer to this domain's subject area (e.g., for an "orders" domain: "purchases",
   "transactions", "sales", "buying")
3. A table list with a one-line summary of each table's purpose, plus 3-5
   keywords per table that a user might search for
4. A relationships section showing how tables connect within the domain
5. A cross-domain relationships section showing connections to other domains
6. A "When to use this domain" section with example question patterns

Keep it concise. Each table summary should be one line.
Do not use contractions.
```

#### Individual table .md files

One LLM call per table. Provide: table name, full column details (names, types, nullability), sample rows, column stats (cardinality, null rates, enum values), relationships, domain context.

Prompt:

```
You are generating a detailed table documentation file for the "{table_name}" table.
This file will be read by an AI agent that is deciding whether to use this table in
a SQL query. The file should give the agent everything it needs to understand what
this table contains and how to use it.

Table: {table_name}
Schema: {schema_name}
Row count: {row_count}

Columns:
{for each column}
- {name} ({type}, {"nullable" if nullable else "not null"}{", PK" if pk}{", default: " + default if default})
  Stats: {distinct_count} distinct values, {null_rate}% null
  {if enum_values}Known values: {enum_values}{end if}
  {if sample_values}Sample values: {sample_values}{end if}
  {if comment}DB comment: {comment}{end if}
{end for}

Sample rows (first {n}):
{formatted sample rows}

Relationships:
{for each relationship involving this table}
- {this_table}.{column} -> {other_table}.{column} ({relationship_type})
{end for}

Generate a markdown file with these exact sections:

# {table_name}
A 1-2 sentence description of what this table contains and represents.

## Keywords
A comma-separated list of alternative terms, synonyms, and related business
concepts that a user might use when they mean this table. For example, if the
table is "fact_orders", keywords might include: purchases, transactions, sales,
buys, bought. Think about what a non-technical business user would call this data.
Format as a single line: "Keywords: term1, term2, term3, ..."
For each column, also include column-level keywords inline in the Columns section.

## Columns
For each column:
- Name, type, constraints
- A human-readable description of what the column contains (infer from name,
  type, and sample values)
- Keywords: alternative terms a user might use for this column, formatted as
  "Keywords: term1, term2, term3" (e.g., for "total_amount" ->
  "Keywords: revenue, sales, price, cost, spend")
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
and sample data. Do not speculate about business logic you cannot verify.
```

#### RELATIONSHIPS.md generation

One LLM call for small databases. Provide: all relationships (explicit and inferred), organized by domain pair.

**Large database batching:** If the total number of relationships exceeds what fits in context (~300+ relationships), batch by domain pair. Generate join path guidance per batch, then do a final merge pass that adds multi-hop cross-batch paths.

Focus on generating "join path" guidance: "To connect customers to their orders, join dim_customer.customer_id = fact_orders.customer_id". Include multi-hop paths where relevant: "To connect customers to products, go through orders: dim_customer -> fact_orders -> order_line_items -> dim_product".

#### GLOSSARY.md generation

One LLM call for small databases. Provide: all table names, column names, enum values, and sample data.

**Large database batching:** If the combined table/column metadata exceeds context limits (roughly 200+ tables), batch by domain. Generate glossary entries per domain, then do a final merge pass to deduplicate and resolve cross-domain terms.

Ask the LLM to generate a mapping of likely business concepts to the physical tables/columns that represent them. For example:
- "customer" -> dim_customer table
- "churn" / "churned" -> dim_customer.is_active = false, or fact_customer_events.event_type = 'churn'
- "revenue" -> fact_orders.total_amount

This is speculative by nature -- include a note at the top saying these mappings are inferred and may need human curation.

#### AMBIGUOUS_TERMS.md generation

After all table .md files and the GLOSSARY.md have been generated, run a keyword conflict detection pass. This is partly programmatic and partly LLM-assisted:

**Step 1 (programmatic):** Parse the `## Keywords` section from every table .md file and the column-level keywords from the `## Columns` sections. Build an inverted index: `keyword -> list of (table, column_or_null)` mappings.

Before flagging conflicts, filter out keyword stopwords -- generic terms that will appear across many tables and produce noise rather than useful disambiguation. Maintain a default stopword list:

```python
KEYWORD_STOPWORDS = {
    # Generic data terms
    "id", "name", "type", "status", "code", "value", "key", "data", "info",
    "number", "count", "total", "amount", "description", "label", "title",
    # Temporal terms
    "date", "time", "timestamp", "created", "updated", "modified", "deleted",
    "start", "end", "day", "month", "year",
    # Boolean/state terms
    "active", "enabled", "flag", "is", "has",
    # Generic entity terms
    "user", "record", "entry", "item", "row", "note", "comment",
}
```

Allow users to extend or override this list via a `keyword_stopwords` config option. After filtering stopwords, any remaining keyword that maps to 2+ tables is a genuine conflict.

**Step 2 (LLM-assisted):** Send the conflict list to the LLM and ask it to generate an AMBIGUOUS_TERMS.md file that:
- Lists each ambiguous term
- Shows all the tables/columns it could refer to
- Provides disambiguation guidance (e.g., "If the user says 'revenue', ask whether they mean gross revenue from `fact_orders.total_amount` or net revenue from `fact_invoices.net_total`. If the context mentions invoicing or billing, prefer `fact_invoices`. If the context mentions sales or purchases, prefer `fact_orders`.")

Prompt:

```
The following terms in this database map to multiple tables or columns,
creating ambiguity for query generation:

{for each conflict}
- "{keyword}":
  - {table_1}.{column_1}: {brief description from table doc}
  - {table_2}.{column_2}: {brief description from table doc}
{end for}

Generate a markdown file that helps an AI agent resolve these ambiguities.
For each ambiguous term:
1. List all tables/columns it could refer to
2. Describe the difference between them
3. Provide context clues that indicate which one the user likely means
   (e.g., "if the user mentions 'monthly billing', prefer fact_invoices;
   if they mention 'checkout' or 'cart', prefer fact_orders")

Do not use contractions.
```

The agent system prompt should reference this file: when the user's question contains a term that could be ambiguous, the agent should check AMBIGUOUS_TERMS.md before proposing tables.

## Query-Time Agent

### Agent Architecture (`agent.py`)

The agent is a loop that navigates the file index, reasons about what to read next, and eventually produces a table selection and SQL query. It uses the LLM as the reasoning engine.

The agent operates with a system prompt and then makes tool calls to read files from the index. The "tools" available to the agent are:

1. `read_file(path, section?)` -- Read a file from the schema index. Path is relative to the index root directory. Returns the file contents. The optional `section` parameter accepts a markdown heading name (e.g., "Columns", "Relationships") and returns only that section, which helps avoid consuming the full context window on large files. If `section` is omitted, returns the entire file.
2. `list_directory(path)` -- List files in a directory. Path is relative to the index root directory. Returns filenames.
3. `propose_tables(selection)` -- Propose a set of tables for the query. This ends the navigation phase. The `selection` parameter is a JSON object:

```json
{
  "tables": [
    {
      "table_name": "dim_customer",
      "schema": "public",
      "columns": ["customer_id", "full_name", "region", "signup_date"],
      "reason": "Contains customer profile data needed for region grouping and signup date filtering"
    }
  ],
  "joins": [
    {
      "left": "dim_customer.customer_id",
      "right": "fact_orders.customer_id",
      "type": "INNER JOIN"
    }
  ],
  "reasoning": "Overall explanation of why these tables and joins answer the question"
}
```

The agent loop:

```
System prompt:
  You are a database expert navigating a schema documentation index to find
  the right tables for a user's SQL query.

  All file paths are relative to the index root directory. Use paths exactly
  as shown below -- do not prepend any absolute path.

  The index is structured as a file hierarchy:
  - INDEX.md: Top-level overview of the database and its domains
  - domains/{name}/DOMAIN.md: Summary of a business domain, its tables, and keywords
  - domains/{name}/tables/{table}.md: Detailed documentation for a single table,
    including keywords/synonyms for the table and each column
  - cross_references/RELATIONSHIPS.md: Join paths between tables
  - cross_references/GLOSSARY.md: Business concept to table/column mapping
  - cross_references/AMBIGUOUS_TERMS.md: Terms that map to multiple tables/columns
    with disambiguation guidance

  Your process:
  1. Start by reading INDEX.md to understand the database landscape
  2. Based on the user's question, identify which domain(s) to explore
  3. Read the relevant DOMAIN.md file(s) to see table summaries and keywords
  4. Read individual table files for tables that look promising -- pay attention
     to the Keywords sections, as users often use different terminology than
     the actual table/column names
  5. Check RELATIONSHIPS.md if you need to join across domains
  6. Check GLOSSARY.md if the user uses business terminology you need to map
  7. Check AMBIGUOUS_TERMS.md if the user's question contains terms that could
     refer to multiple tables or columns -- resolve the ambiguity before
     proposing tables

  You can read files in any order and backtrack if needed. Read the minimum
  number of files necessary to confidently select the right tables.

  When you are confident you have identified the right tables, call
  propose_tables with your selection and reasoning.

User message:
  Question: "{user's natural language question}"

  Find the tables, columns, and join paths needed to answer this question.
```

The agent makes tool calls iteratively. After each tool call returns file contents, the LLM decides what to read next or whether to propose tables. The `max_navigation_steps` config parameter limits total file reads.

Implementation note: this is a standard tool-use loop. Send messages to the LLM, if the response contains tool calls, execute them and send results back, repeat until the LLM produces a final text response or calls `propose_tables`.

**Navigation exhaustion fallback:** If the agent reaches `max_navigation_steps` without calling `propose_tables`, do not silently fail or force a proposal from incomplete information. Instead:
1. Inject a final system message into the conversation: "You have reached the maximum number of navigation steps. Based on everything you have read so far, either call propose_tables with your best selection and note any uncertainty, or explain why you could not find suitable tables."
2. Give the LLM one more turn to respond.
3. If it calls `propose_tables`, proceed normally but flag the result to the user: "Note: the agent used all 20 navigation steps, which may indicate the question spans many domains or the index needs refinement."
4. If it still does not call `propose_tables`, display to the user: "I explored 20 files but could not confidently identify the right tables for this question. Files read: [list]. Could you provide more specifics, or try narrowing the question to a single domain?"

### Table Confirmation

If `confirm_tables` is true, after the agent proposes tables, display (include schema prefix when the database has multiple schemas):

```
Proposed tables for your query:

  1. public.dim_customer -- Customer profile data (name, region, signup date)
     Columns: customer_id, full_name, region, signup_date
  2. public.fact_orders -- Order transactions with amounts and dates
     Columns: order_id, customer_id, order_date, total_amount

  Join path: public.dim_customer.customer_id = public.fact_orders.customer_id

  Reasoning: Your question asks about customer signups by region, which
  requires the customer profile table filtered by signup date, with order
  data for the "who placed orders" filter.

Accept these tables? [Y/n/edit]
```

If the user types `n` or `edit`, let them type a correction (e.g., "also include the customer_segments table" or "use fact_subscriptions instead of fact_orders"), and re-run the agent with that additional context.

### SQL Generation (`sql_generator.py`)

After tables are confirmed, make a final LLM call to generate SQL.

Prompt:

```
You are a SQL expert generating a query for a {dialect} database.

User's question: "{question}"

Selected tables and their schemas:
{for each selected table, include the full contents of its .md file}

Join paths:
{relevant section from RELATIONSHIPS.md}

Generate a SQL query that answers the user's question.

Rules:
- Use only the tables and columns documented above
- Do not reference any table or column not in the provided documentation
- Include appropriate JOINs based on the documented relationships
- Add comments explaining non-obvious parts of the query
- Use the correct SQL dialect for {dialect}
- If the question is ambiguous, state your interpretation before the SQL

Respond with:
1. Your interpretation of the question (one sentence)
2. The SQL query in a code block
3. A brief explanation of how the query works
```

### Error Handling in SQL Generation

If `--execute` is set and the query fails, capture the full error message from the database. Send the error back to the LLM along with the original query, question, and table documentation. Ask it to fix all errors it can identify (addressing feedback point #2 from the Uber employee -- find all errors, not just the first one).

Prompt for error correction (note: the SQL block within this prompt must be delimited with a different marker than the outer prompt template -- use triple tildes `~~~sql` or string interpolation, not nested triple backticks):

```
The following SQL query failed when executed:

~~~sql
{failed_query}
~~~

Error message:
{error_message}

Original question: "{question}"

Table documentation:
{table_docs}

Analyze the query and identify ALL errors, not just the first one.
For each error, explain what went wrong and how to fix it.
Then provide a corrected query that addresses all issues.
```

Allow up to 3 retry attempts before giving up.

## LLM Provider Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class LLMMessage:
    role: str                     # "system", "user", "assistant", "tool"
    content: str
    tool_call_id: str | None = None
    tool_calls: list | None = None

@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict              # JSON Schema

class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
    ) -> LLMMessage:
        """Send a completion request and return the response."""
        pass

    @abstractmethod
    def complete_json(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.0,
    ) -> dict:
        """Send a completion request expecting a JSON response."""
        pass
```

Both providers (Anthropic, OpenAI) implement this interface. The tool-use protocol differs between providers, so each implementation handles the translation internally.

The Anthropic provider uses the Messages API (`messages.create`). The OpenAI provider uses the Responses API (`responses.create`), which represents tool calls as top-level `function_call` input items rather than nesting them inside assistant messages (see `_prepare_input()` in `openai_provider.py`).

## Dependencies

```
# pyproject.toml [project.dependencies]
sqlalchemy>=2.0
click>=8.0
rich>=13.0
anthropic>=0.40.0
openai>=1.0
pyyaml>=6.0
```

No vector database. No embedding model. No LangChain.

## Cost Estimation

For a database with N tables:

**Indexing (one-time):**
- 1 LLM call for domain clustering
- 1 call for INDEX.md
- ~D calls for DOMAIN.md files (D = number of domains, typically 3-15)
- N calls for individual table files
- 1 call for RELATIONSHIPS.md
- 1 call for GLOSSARY.md
- 1 call for AMBIGUOUS_TERMS.md (keyword conflict resolution)
- Total: approximately N + D + 5 calls

For a 100-table database, expect roughly 110-120 LLM calls during indexing. With Sonnet, this is on the order of a few dollars.

**Per query:**
- Navigation: typically 3-7 file reads, each requiring one LLM call in the tool-use loop
- SQL generation: 1 call
- Error correction: 0-3 calls
- Total: approximately 4-10 calls per query

## Future Considerations (Out of Scope for Now)

- Auto-refresh on schema changes (webhook or cron-based diff)
- Security/access control (respecting database permissions during sampling)
- Human curation UI for editing generated descriptions and glossary
- Query history tracking to improve table selection over time
- Multi-database index (navigate across multiple connected databases)
- Caching of agent navigation paths for repeated question patterns