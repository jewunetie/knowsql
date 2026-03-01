"""SQL generation from selected tables."""

import logging
from dataclasses import dataclass, field

from sqlalchemy import create_engine, text

from knowsql.llm.provider import LLMMessage

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


@dataclass
class SQLResult:
    interpretation: str | None = None
    sql: str = ""
    explanation: str | None = None
    executed: bool = False
    results: list[tuple] | None = None
    columns: list[str] = field(default_factory=list)
    error: str | None = None


def generate_sql(question, proposal, navigator, llm, dialect="sql", connection_string=None) -> SQLResult:
    """Generate SQL for the question using the proposal."""
    if not proposal.tables:
        return SQLResult(
            interpretation="No tables were identified for this question.",
            explanation=proposal.reasoning,
        )

    # Load full table documentation for selected tables
    table_docs = []
    for table_info in proposal.tables:
        table_name = table_info["table_name"]
        content = navigator.find_and_read_table(table_name)
        if content:
            table_docs.append(f"### {table_name}\n{content}")
        else:
            table_docs.append(f"### {table_name}\n(Documentation not found)")

    # Load relevant relationships (filter to only selected tables)
    full_rel_content = navigator.read_file("cross_references/RELATIONSHIPS.md")
    selected_names = {t.get("table_name", "").lower() for t in proposal.tables}
    rel_lines = []
    for line in full_rel_content.split("\n"):
        line_lower = line.lower()
        if any(name in line_lower for name in selected_names if name):
            rel_lines.append(line)
    rel_content = "\n".join(rel_lines) if rel_lines else "(No specific relationships found for selected tables)"

    # Build join info
    join_lines = []
    for join in proposal.joins:
        join_type = join.get("type", "JOIN")
        join_lines.append(f"- {join['left']} = {join['right']} ({join_type})")

    prompt = f"""You are a SQL expert generating a query for a {dialect} database.

User's question: "{question}"

Selected tables and their schemas:
{chr(10).join(table_docs)}

Proposed join paths:
{chr(10).join(join_lines) if join_lines else "(see relationships documentation below)"}

Relationships reference:
{rel_content}

Agent's reasoning for table selection:
{proposal.reasoning}

Generate a SQL query that answers the user's question.

Rules:
- Use only the tables and columns documented above
- Do not reference any table or column not in the provided documentation
- Include appropriate JOINs based on the documented relationships
- Add comments explaining non-obvious parts of the query
- Use the correct SQL dialect for {dialect}
- If the question is ambiguous, state your interpretation before the SQL

Respond with:
1. Your interpretation of the question (one sentence, on a line starting with "Interpretation:")
2. The SQL query in a ```sql code block
3. A brief explanation of how the query works (on lines starting with "Explanation:")"""

    messages = [LLMMessage(role="user", content=prompt)]
    response = llm.complete(messages)

    result = _parse_sql_response(response.content)

    # Execute if requested
    if connection_string and result.sql:
        result = _execute_and_retry(
            result, question, table_docs, llm, dialect, connection_string,
        )

    return result


def _execute_and_retry(result, question, table_docs, llm, dialect, connection_string) -> SQLResult:
    """Execute SQL and retry on failure."""
    engine = create_engine(connection_string)

    for attempt in range(MAX_RETRIES + 1):
        try:
            with engine.connect() as conn:
                query_result = conn.execute(text(result.sql))
                columns = list(query_result.keys())
                rows = query_result.fetchall()
                result.executed = True
                result.columns = columns
                result.results = [tuple(row) for row in rows]
                result.error = None
                return result
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"SQL execution failed (attempt {attempt + 1}): {error_msg}")

            if attempt >= MAX_RETRIES:
                result.error = f"Query failed after {MAX_RETRIES + 1} attempts: {error_msg}"
                return result

            # Ask LLM to fix the query
            fix_prompt = f"""The following SQL query failed when executed:

~~~sql
{result.sql}
~~~

Error message:
{error_msg}

Original question: "{question}"

Table documentation:
{chr(10).join(table_docs)}

Analyze the query and identify ALL errors, not just the first one.
For each error, explain what went wrong and how to fix it.
Then provide a corrected query in a ```sql code block."""

            messages = [LLMMessage(role="user", content=fix_prompt)]
            response = llm.complete(messages)
            fixed = _parse_sql_response(response.content)
            if fixed.sql:
                result.sql = fixed.sql
                if fixed.interpretation:
                    result.interpretation = fixed.interpretation
                if fixed.explanation:
                    result.explanation = fixed.explanation

    return result


def _parse_sql_response(content: str) -> SQLResult:
    """Parse LLM response to extract interpretation, SQL, and explanation."""
    interpretation = None
    sql = ""
    explanation = None

    lines = content.split("\n")

    # Extract interpretation
    for line in lines:
        if line.strip().startswith("Interpretation:"):
            interpretation = line.strip()[len("Interpretation:"):].strip()
            break

    # Extract SQL from code block (supports ```sql and ~~~sql fences)
    in_sql = False
    sql_lines = []
    fence_marker = None
    for line in lines:
        stripped = line.strip()
        if not in_sql and (stripped.startswith("```sql") or stripped.startswith("~~~sql")):
            in_sql = True
            fence_marker = stripped[:3]  # ``` or ~~~
            continue
        elif in_sql and stripped == fence_marker:
            in_sql = False
            fence_marker = None
            continue
        elif in_sql:
            sql_lines.append(line)

    sql = "\n".join(sql_lines).strip()

    # Extract explanation
    explanation_lines = []
    in_explanation = False
    for line in lines:
        if line.strip().startswith("Explanation:"):
            in_explanation = True
            explanation_lines.append(line.strip()[len("Explanation:"):].strip())
            continue
        elif in_explanation:
            if line.strip().startswith("```") or line.strip().startswith("Interpretation:"):
                break
            explanation_lines.append(line.strip())

    if explanation_lines:
        explanation = " ".join(l for l in explanation_lines if l)

    return SQLResult(
        interpretation=interpretation,
        sql=sql,
        explanation=explanation,
    )
