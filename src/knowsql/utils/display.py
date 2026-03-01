"""Rich-based display utilities for KnowSQL."""

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.syntax import Syntax
from rich.table import Table
from rich.panel import Panel

console = Console()


def create_indexing_progress():
    """Create a Rich progress bar for indexing."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )


def display_sql(sql: str, interpretation: str | None = None, explanation: str | None = None):
    """Display a SQL query with syntax highlighting."""
    if interpretation:
        console.print(f"\n[bold]Interpretation:[/bold] {interpretation}")
    if sql:
        syntax = Syntax(sql, "sql", theme="monokai", line_numbers=True)
        console.print(Panel(syntax, title="Generated SQL", border_style="blue"))
    if explanation:
        console.print(f"\n[bold]Explanation:[/bold] {explanation}")


def display_results_table(columns: list[str], rows: list[tuple]):
    """Display query results as a Rich table."""
    table = Table(show_header=True, header_style="bold magenta")
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*[str(v) if v is not None else "NULL" for v in row])
    console.print(table)


def display_privacy_warning(provider: str) -> bool:
    """Display privacy warning and get confirmation."""
    console.print(Panel(
        f"[bold yellow]WARNING:[/bold yellow] This tool will send sample row data from your "
        f"database to [bold]{provider}[/bold]. If your database contains PII, PHI, financial "
        f"data, or other sensitive information, consider using [bold]--no-sample-data[/bold] to "
        f"skip row sampling (descriptions will be less accurate but no row data will leave "
        f"your network).",
        title="Data Privacy Notice",
        border_style="yellow",
    ))
    response = console.input("Continue with data sampling? [y/N] ").strip().lower()
    return response in ("y", "yes")


def display_table_proposal(proposal):
    """Display the agent's table proposal."""
    if not proposal.tables:
        console.print("[yellow]No tables proposed.[/yellow]")
        if proposal.reasoning:
            console.print(f"\n{proposal.reasoning}")
        return

    console.print("\n[bold]Proposed tables for your query:[/bold]\n")
    for i, table in enumerate(proposal.tables, 1):
        schema_prefix = f"{table.get('schema', '')}." if table.get("schema") else ""
        table_name = table.get("table_name", "unknown")
        console.print(f"  {i}. [bold]{schema_prefix}{table_name}[/bold] -- {table.get('reason', '')}")
        if table.get("columns"):
            console.print(f"     Columns: {', '.join(table['columns'])}")

    if proposal.joins:
        console.print("\n  [bold]Join paths:[/bold]")
        for join in proposal.joins:
            console.print(f"    {join.get('left', '?')} = {join.get('right', '?')} ({join.get('type', 'JOIN')})")

    if proposal.reasoning:
        console.print(f"\n  [bold]Reasoning:[/bold] {proposal.reasoning}")
    console.print()


def display_navigation_step(step: int, tool_name: str, args: dict):
    """Display a navigation step for --show-navigation mode."""
    if tool_name == "read_file":
        path = args.get("path", "")
        section = args.get("section")
        detail = f"{path}" + (f" (section: {section})" if section else "")
    elif tool_name == "list_directory":
        detail = args.get("path", "")
    elif tool_name == "propose_tables":
        detail = "Proposing tables..."
    else:
        detail = str(args)
    console.print(f"  [dim]Step {step}:[/dim] {tool_name}({detail})")
