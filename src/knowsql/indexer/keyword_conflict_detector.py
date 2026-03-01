"""Keyword conflict detection and AMBIGUOUS_TERMS.md generation."""

import logging
import re
from pathlib import Path
from collections import defaultdict

from knowsql.llm.provider import LLMMessage

logger = logging.getLogger(__name__)

# Default stopwords that produce noise rather than useful disambiguation
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


def detect_keyword_conflicts(
    output_dir: str,
    llm,
    stopwords_extend: list[str] | None = None,
    stopwords_override: list[str] | None = None,
) -> str:
    """Parse keywords from generated table files, detect conflicts, generate AMBIGUOUS_TERMS.md."""
    root = Path(output_dir)

    # Build stopword set
    if stopwords_override is not None:
        stopwords = set(w.lower() for w in stopwords_override)
    else:
        stopwords = set(KEYWORD_STOPWORDS)
        if stopwords_extend:
            stopwords.update(w.lower() for w in stopwords_extend)

    # Parse all table .md files for keywords
    inverted_index = defaultdict(list)  # keyword -> [(table, column_or_none)]
    domains_dir = root / "domains"

    if not domains_dir.exists():
        return "# Ambiguous Terms\n\nNo table documentation found."

    for domain_dir in domains_dir.iterdir():
        if not domain_dir.is_dir():
            continue
        tables_dir = domain_dir / "tables"
        if not tables_dir.exists():
            continue
        for table_file in tables_dir.iterdir():
            if not table_file.suffix == ".md" or table_file.name.endswith("_columns_detail.md"):
                continue
            table_name = table_file.stem
            _parse_keywords_from_file(table_file, table_name, inverted_index)

    # Filter stopwords and find conflicts (keywords mapping to 2+ tables)
    conflicts = {}
    for keyword, mappings in inverted_index.items():
        if keyword.lower() in stopwords:
            continue
        # Get unique tables
        unique_tables = set(table for table, _ in mappings)
        if len(unique_tables) >= 2:
            conflicts[keyword] = mappings

    if not conflicts:
        content = "# Ambiguous Terms\n\nNo ambiguous terms detected in this database.\n"
        (root / "cross_references" / "AMBIGUOUS_TERMS.md").write_text(content)
        return content

    # Generate AMBIGUOUS_TERMS.md via LLM
    conflict_lines = []
    for keyword, mappings in sorted(conflicts.items()):
        conflict_lines.append(f'- "{keyword}":')
        for table, column in mappings:
            if column:
                conflict_lines.append(f"  - {table}.{column}")
            else:
                conflict_lines.append(f"  - {table} (table-level keyword)")

    prompt = f"""The following terms in this database map to multiple tables or columns,
creating ambiguity for query generation:

{chr(10).join(conflict_lines)}

Generate a markdown file that helps an AI agent resolve these ambiguities.
For each ambiguous term:
1. List all tables/columns it could refer to
2. Describe the difference between them
3. Provide context clues that indicate which one the user likely means
   (e.g., "if the user mentions 'monthly billing', prefer invoices;
   if they mention 'checkout' or 'cart', prefer orders")

Do not use contractions."""

    messages = [LLMMessage(role="user", content=prompt)]
    response = llm.complete(messages)
    content = response.content

    (root / "cross_references" / "AMBIGUOUS_TERMS.md").write_text(content)
    return content


def _parse_keywords_from_file(filepath: Path, table_name: str, inverted_index: dict):
    """Parse Keywords lines from a table markdown file."""
    content = filepath.read_text()
    lines = content.split("\n")

    current_column = None
    in_columns_section = False

    for line in lines:
        stripped = line.strip()

        # Track which section we're in
        if stripped.startswith("## "):
            section_name = stripped[3:].strip().lower()
            in_columns_section = section_name == "columns"
            current_column = None
            continue

        # Track current column in columns section
        if in_columns_section and stripped.startswith("### "):
            current_column = stripped[4:].strip()
            continue

        # Also detect column names from "- **column_name**" or "- `column_name`" patterns
        if in_columns_section:
            col_match = re.match(r"^[-*]\s+\*\*(\w+)\*\*", stripped)
            if not col_match:
                col_match = re.match(r"^[-*]\s+`(\w+)`", stripped)
            if col_match:
                current_column = col_match.group(1)

        # Parse "Keywords: ..." lines
        kw_match = re.match(r"(?:Keywords|keywords)\s*:\s*(.+)", stripped)
        if kw_match:
            keywords_str = kw_match.group(1)
            keywords = [k.strip().lower() for k in keywords_str.split(",") if k.strip()]
            for kw in keywords:
                # Skip multi-word keywords (more than 3 words) as they're phrases
                if len(kw.split()) > 3:
                    continue
                inverted_index[kw].append((table_name, current_column if in_columns_section else None))
