"""Agent core - tool-use loop for navigating the schema index."""

import json
import logging
from dataclasses import dataclass, field

from knowsql.llm.provider import LLMMessage, ToolDefinition, ToolCall
from knowsql.utils.display import display_navigation_step

logger = logging.getLogger(__name__)


@dataclass
class TableProposal:
    tables: list[dict] = field(default_factory=list)
    joins: list[dict] = field(default_factory=list)
    reasoning: str = ""
    files_read: list[str] = field(default_factory=list)
    exhausted: bool = False


# Tool definitions for the agent
AGENT_TOOLS = [
    ToolDefinition(
        name="read_file",
        description="Read a file from the schema index. Path is relative to the index root directory. Returns the file contents. The optional 'section' parameter accepts a markdown heading name (e.g., 'Columns', 'Relationships') and returns only that section.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file (e.g., 'INDEX.md', 'domains/orders/DOMAIN.md')",
                },
                "section": {
                    "type": "string",
                    "description": "Optional markdown heading name to extract only that section",
                },
            },
            "required": ["path"],
        },
    ),
    ToolDefinition(
        name="list_directory",
        description="List files in a directory within the schema index. Path is relative to the index root directory.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the directory (e.g., 'domains/', 'domains/orders/tables/')",
                },
            },
            "required": ["path"],
        },
    ),
    ToolDefinition(
        name="propose_tables",
        description="Propose a set of tables for answering the user's query. Call this when you have identified the right tables. This ends the navigation phase.",
        parameters={
            "type": "object",
            "properties": {
                "tables": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "table_name": {"type": "string"},
                            "schema": {"type": "string"},
                            "columns": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "reason": {"type": "string"},
                        },
                        "required": ["table_name", "reason"],
                    },
                },
                "joins": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "left": {"type": "string"},
                            "right": {"type": "string"},
                            "type": {"type": "string"},
                        },
                        "required": ["left", "right"],
                    },
                },
                "reasoning": {"type": "string"},
            },
            "required": ["tables", "reasoning"],
        },
    ),
]

SYSTEM_PROMPT = """You are a database expert navigating a schema documentation index to find
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
propose_tables with your selection and reasoning."""


def run_agent(
    question: str,
    navigator,
    llm,
    max_steps: int = 20,
    show_navigation: bool = False,
    conversation_history: list | None = None,
    user_correction: str | None = None,
) -> TableProposal:
    """Run the agent loop to find relevant tables for a question."""
    # Build initial messages
    messages = [LLMMessage(role="system", content=SYSTEM_PROMPT)]

    # Add conversation history for REPL context (keep last 10 entries to avoid context overflow)
    if conversation_history:
        recent_history = conversation_history[-10:]
        history_text = "Previous questions in this session:\n"
        for entry in recent_history:
            history_text += f"- Q: {entry['question']}\n"
            if entry.get("tables"):
                history_text += f"  Tables used: {', '.join(entry['tables'])}\n"
            if entry.get("sql"):
                history_text += f"  SQL: {entry['sql'][:200]}\n"
        messages.append(LLMMessage(role="user", content=history_text))
        messages.append(LLMMessage(role="assistant", content="I understand the prior context. What is your next question?"))

    user_msg = f'Question: "{question}"\n\nFind the tables, columns, and join paths needed to answer this question.'
    if user_correction:
        user_msg += f"\n\nUser correction from previous attempt: {user_correction}"
    messages.append(LLMMessage(role="user", content=user_msg))

    files_read = []
    step_count = 0

    while step_count < max_steps:
        response = llm.complete(messages, tools=AGENT_TOOLS)
        messages.append(response)

        # If no tool calls, the agent is done (text-only response)
        if not response.tool_calls:
            # Agent responded with text but no proposal - try to extract reasoning
            return TableProposal(
                reasoning=response.content,
                files_read=files_read,
            )

        # Process all tool calls
        for tool_call in response.tool_calls:
            step_count += 1

            if show_navigation:
                display_navigation_step(step_count, tool_call.name, tool_call.arguments)

            if tool_call.name == "propose_tables":
                args = tool_call.arguments
                return TableProposal(
                    tables=args.get("tables", []),
                    joins=args.get("joins", []),
                    reasoning=args.get("reasoning", ""),
                    files_read=files_read,
                )
            elif tool_call.name == "read_file":
                path = tool_call.arguments.get("path", "")
                section = tool_call.arguments.get("section")
                content = navigator.read_file(path, section)
                files_read.append(path)
                messages.append(LLMMessage(
                    role="tool",
                    content=content,
                    tool_call_id=tool_call.id,
                ))
            elif tool_call.name == "list_directory":
                path = tool_call.arguments.get("path", "")
                content = navigator.list_directory(path)
                messages.append(LLMMessage(
                    role="tool",
                    content=content,
                    tool_call_id=tool_call.id,
                ))
            else:
                messages.append(LLMMessage(
                    role="tool",
                    content=f"Unknown tool: {tool_call.name}",
                    tool_call_id=tool_call.id,
                ))

    # Navigation exhausted - give one more chance
    messages.append(LLMMessage(
        role="user",
        content="You have reached the maximum number of navigation steps. Based on everything you have read so far, either call propose_tables with your best selection and note any uncertainty, or explain why you could not find suitable tables.",
    ))

    response = llm.complete(messages, tools=AGENT_TOOLS)

    if response.tool_calls:
        for tool_call in response.tool_calls:
            if tool_call.name == "propose_tables":
                args = tool_call.arguments
                return TableProposal(
                    tables=args.get("tables", []),
                    joins=args.get("joins", []),
                    reasoning=args.get("reasoning", ""),
                    files_read=files_read,
                    exhausted=True,
                )

    return TableProposal(
        reasoning=response.content or "Could not identify suitable tables within the navigation limit.",
        files_read=files_read,
        exhausted=True,
    )
