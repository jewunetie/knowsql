"""LLM-based domain clustering for tables."""

import logging

from knowsql.indexer.models import DatabaseMetadata, DomainCluster
from knowsql.llm.provider import LLMMessage

logger = logging.getLogger(__name__)

BATCH_SIZE = 100


def cluster_domains(db_metadata: DatabaseMetadata, llm) -> list[DomainCluster]:
    """Cluster tables into business domains using LLM."""
    tables = db_metadata.tables

    if len(tables) <= BATCH_SIZE * 2:
        # Small enough for single call
        raw_domains = _cluster_batch(tables, llm)
    else:
        # Large DB: batch clustering + merge
        raw_domains = _cluster_large_db(tables, llm)

    # MECE validation
    all_table_names = {t.name for t in tables}
    raw_domains = _validate_mece(raw_domains, all_table_names, tables, llm)

    # Convert to DomainCluster objects
    clusters = []
    for name, info in raw_domains.items():
        clusters.append(DomainCluster(
            name=name,
            description=info.get("description", ""),
            tables=info.get("tables", []),
            also_relevant_to=info.get("also_relevant_to", {}),
        ))

    return clusters


def _cluster_batch(tables, llm) -> dict:
    """Cluster a batch of tables."""
    table_lines = []
    for t in tables:
        col_names = ", ".join(c.name for c in t.columns)
        table_lines.append(f"- {t.name}: {col_names}")

    table_text = "\n".join(table_lines)

    messages = [
        LLMMessage(role="system", content="You are a database schema analyst. Respond only in valid JSON."),
        LLMMessage(role="user", content=f"""You are analyzing a database schema to organize tables into business domains.

Here are all the tables in the database with their columns:

{table_text}

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
{{
  "domains": {{
    "domain_name": {{
      "description": "One sentence describing what this domain covers",
      "tables": ["table1", "table2"],
      "also_relevant_to": {{"table1": ["other-domain"]}}
    }}
  }}
}}"""),
    ]

    result = llm.complete_json(messages)
    return result.get("domains", result)


def _cluster_large_db(tables, llm) -> dict:
    """Cluster a large database in batches then merge."""
    batches = []
    for i in range(0, len(tables), BATCH_SIZE):
        batches.append(tables[i:i + BATCH_SIZE])

    all_domains = {}
    for batch in batches:
        batch_domains = _cluster_batch(batch, llm)
        for name, info in batch_domains.items():
            if name in all_domains:
                all_domains[name]["tables"].extend(info.get("tables", []))
                existing_relevance = all_domains[name].get("also_relevant_to", {})
                existing_relevance.update(info.get("also_relevant_to", {}))
                all_domains[name]["also_relevant_to"] = existing_relevance
            else:
                all_domains[name] = info

    # Merge pass
    domain_summary = {name: {"description": info.get("description", ""), "tables": info.get("tables", [])}
                      for name, info in all_domains.items()}

    messages = [
        LLMMessage(role="system", content="You are a database schema analyst. Respond only in valid JSON."),
        LLMMessage(role="user", content=f"""These domains were generated from batched clustering. Review and consolidate:

{_format_domains_for_merge(domain_summary)}

Consolidate similar domains and ensure clean naming. Return the final mapping in JSON:
{{
  "domains": {{
    "domain_name": {{
      "description": "...",
      "tables": ["..."],
      "also_relevant_to": {{}}
    }}
  }}
}}"""),
    ]

    result = llm.complete_json(messages)
    return result.get("domains", result)


def _validate_mece(domains: dict, all_table_names: set, tables, llm) -> dict:
    """Validate MECE properties and fix violations."""
    # Exhaustive check: find missing tables
    assigned_tables = set()
    for info in domains.values():
        assigned_tables.update(info.get("tables", []))

    missing = all_table_names - assigned_tables

    if missing:
        logger.warning(f"MECE violation: {len(missing)} tables missing from clustering: {missing}")
        # Ask LLM to assign missing tables
        missing_tables = [t for t in tables if t.name in missing]
        domain_names = list(domains.keys())

        table_lines = []
        for t in missing_tables:
            col_names = ", ".join(c.name for c in t.columns)
            table_lines.append(f"- {t.name}: {col_names}")

        messages = [
            LLMMessage(role="system", content="You are a database schema analyst. Respond only in valid JSON."),
            LLMMessage(role="user", content=f"""The following tables were not assigned to any domain:

{chr(10).join(table_lines)}

Existing domains: {', '.join(domain_names)}

Assign each table to the most appropriate existing domain, or create a new domain if none fit.

Respond in JSON:
{{
  "assignments": {{
    "table_name": "domain_name"
  }}
}}"""),
        ]

        result = llm.complete_json(messages)
        assignments = result.get("assignments", {})
        for table_name, domain_name in assignments.items():
            if domain_name not in domains:
                domains[domain_name] = {
                    "description": f"Domain for {domain_name}",
                    "tables": [],
                    "also_relevant_to": {},
                }
            domains[domain_name]["tables"].append(table_name)

    # Exclusive check: deduplicate
    seen = {}
    for domain_name, info in domains.items():
        deduped = []
        for table in info.get("tables", []):
            if table in seen:
                logger.warning(f"MECE violation: {table} in both {seen[table]} and {domain_name}, keeping first")
            else:
                seen[table] = domain_name
                deduped.append(table)
        info["tables"] = deduped

    # Remove empty domains
    domains = {name: info for name, info in domains.items() if info.get("tables")}

    return domains


def _format_domains_for_merge(domains: dict) -> str:
    lines = []
    for name, info in domains.items():
        table_list = info.get("tables", [])
        tables = ", ".join(table_list[:10])
        if len(table_list) > 10:
            tables += f"... (+{len(table_list) - 10} more)"
        lines.append(f"- {name}: {info.get('description', '')} [{tables}]")
    return "\n".join(lines)
