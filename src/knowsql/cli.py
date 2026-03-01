"""KnowSQL CLI interface."""

import logging
import sys

import click

from knowsql.utils.display import console


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def cli(verbose):
    """KnowSQL: SQL Schema Discovery Agent.

    Solves the 'which tables should I query?' problem for any SQL database.
    """
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(name)s %(levelname)s: %(message)s",
    )


@cli.command()
@click.option("--connection-string", required=True, help="SQLAlchemy connection string")
@click.option("--output-dir", default="./schema_index", help="Output directory for the index")
@click.option("--provider", type=click.Choice(["anthropic", "openai"]), help="LLM provider")
@click.option("--model", help="Model identifier")
@click.option("--yes", "-y", is_flag=True, help="Skip interactive confirmations")
@click.option("--no-sample-data", is_flag=True, help="Skip all data sampling")
@click.option("--sample-schema-only", is_flag=True, help="Run aggregate stats only, no row data")
def index(connection_string, output_dir, provider, model, yes, no_sample_data, sample_schema_only):
    """Index a database schema for query discovery."""
    from knowsql.config import load_config
    from knowsql.indexer.pipeline import run_indexing_pipeline

    config = load_config(
        provider=provider,
        model=model,
        output_dir=output_dir,
        sample_mode="none" if no_sample_data else ("schema-only" if sample_schema_only else None),
    )

    try:
        run_indexing_pipeline(config, connection_string, yes=yes)
    except KeyboardInterrupt:
        console.print("\n[yellow]Indexing interrupted.[/yellow]")
        sys.exit(1)
    except Exception as e:
        _handle_error(e)


@cli.command()
@click.option("--question", required=True, help="Natural language question")
@click.option("--index-dir", default="./schema_index", help="Path to the schema index")
@click.option("--connection-string", help="Connection string for query execution")
@click.option("--provider", type=click.Choice(["anthropic", "openai"]), help="LLM provider")
@click.option("--model", help="Model identifier")
@click.option("--execute", is_flag=True, help="Execute the generated SQL")
@click.option("--show-navigation", is_flag=True, help="Show agent file reads")
def query(question, index_dir, connection_string, provider, model, execute, show_navigation):
    """Ask a natural language question about your database."""
    from knowsql.config import load_config
    from knowsql.agent.agent import run_agent
    from knowsql.agent.navigator import IndexNavigator
    from knowsql.agent.table_selector import confirm_table_selection
    from knowsql.agent.sql_generator import generate_sql
    from knowsql.llm import create_provider
    from knowsql.utils.display import display_sql, display_results_table

    config = load_config(provider=provider, model=model, index_dir=index_dir)

    try:
        llm = create_provider(config.llm)
        navigator = IndexNavigator(config.agent.index_dir)

        if show_navigation:
            console.print("[dim]Navigation trace:[/dim]")

        proposal = run_agent(
            question=question,
            navigator=navigator,
            llm=llm,
            max_steps=config.agent.max_navigation_steps,
            show_navigation=show_navigation,
        )

        if proposal.exhausted:
            console.print(
                f"[yellow]Note: the agent used all {config.agent.max_navigation_steps} "
                f"navigation steps. Files read: {', '.join(proposal.files_read)}[/yellow]"
            )

        if config.agent.confirm_tables:
            accepted, correction = confirm_table_selection(proposal)
            if not accepted and correction:
                proposal = run_agent(
                    question=question,
                    navigator=navigator,
                    llm=llm,
                    max_steps=config.agent.max_navigation_steps,
                    show_navigation=show_navigation,
                    user_correction=correction,
                )

        result = generate_sql(
            question=question,
            proposal=proposal,
            navigator=navigator,
            llm=llm,
            dialect=navigator.get_dialect(),
            connection_string=connection_string if execute else None,
        )

        console.print()
        display_sql(result.sql, result.interpretation, result.explanation)
        if result.executed and result.results is not None:
            display_results_table(result.columns, result.results)
        elif result.error:
            console.print(f"[red]Error:[/red] {result.error}")

    except KeyboardInterrupt:
        console.print("\n[yellow]Query interrupted.[/yellow]")
        sys.exit(1)
    except Exception as e:
        _handle_error(e)


@cli.command()
@click.option("--index-dir", default="./schema_index", help="Path to the schema index")
@click.option("--connection-string", help="Connection string for query execution")
@click.option("--provider", type=click.Choice(["anthropic", "openai"]), help="LLM provider")
@click.option("--model", help="Model identifier")
def repl(index_dir, connection_string, provider, model):
    """Interactive query session."""
    from knowsql.config import load_config
    from knowsql.agent.agent import run_agent
    from knowsql.agent.navigator import IndexNavigator
    from knowsql.agent.table_selector import confirm_table_selection
    from knowsql.agent.sql_generator import generate_sql
    from knowsql.llm import create_provider
    from knowsql.utils.display import display_sql, display_results_table

    config = load_config(provider=provider, model=model, index_dir=index_dir)

    try:
        llm = create_provider(config.llm)
    except Exception as e:
        _handle_error(e)
        return

    navigator = IndexNavigator(config.agent.index_dir)

    console.print("[bold]KnowSQL Interactive Session[/bold]")
    console.print("Type your question, or use /tables, /domains, /inspect <table>, /clear, /exit")
    console.print()

    conversation_history = []

    while True:
        try:
            user_input = console.input("[bold green]knowsql>[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input == "/exit":
            console.print("Goodbye!")
            break
        elif user_input == "/clear":
            conversation_history = []
            console.print("Conversation context cleared.")
            continue
        elif user_input == "/tables":
            tables = navigator.list_all_tables()
            for t in tables:
                console.print(f"  {t}")
            continue
        elif user_input == "/domains":
            domains = navigator.list_domains()
            for d in domains:
                console.print(f"  {d}")
            continue
        elif user_input.startswith("/inspect "):
            table_name = user_input[9:].strip()
            content = navigator.find_and_read_table(table_name)
            if content:
                console.print(content)
            else:
                console.print(f"[red]Table '{table_name}' not found in index.[/red]")
            continue

        try:
            proposal = run_agent(
                question=user_input,
                navigator=navigator,
                llm=llm,
                max_steps=config.agent.max_navigation_steps,
                show_navigation=False,
                conversation_history=conversation_history,
            )

            if config.agent.confirm_tables and proposal.tables:
                accepted, correction = confirm_table_selection(proposal)
                if not accepted and correction:
                    proposal = run_agent(
                        question=user_input,
                        navigator=navigator,
                        llm=llm,
                        max_steps=config.agent.max_navigation_steps,
                        show_navigation=False,
                        user_correction=correction,
                        conversation_history=conversation_history,
                    )

            result = generate_sql(
                question=user_input,
                proposal=proposal,
                navigator=navigator,
                llm=llm,
                dialect=navigator.get_dialect(),
                connection_string=connection_string if connection_string else None,
            )

            display_sql(result.sql, result.interpretation, result.explanation)
            if result.executed and result.results is not None:
                display_results_table(result.columns, result.results)
            elif result.error:
                console.print(f"[red]Error:[/red] {result.error}")

            conversation_history.append({
                "question": user_input,
                "tables": [t["table_name"] for t in proposal.tables] if proposal.tables else [],
                "sql": result.sql,
            })

        except KeyboardInterrupt:
            console.print("\n[yellow]Query interrupted. Type /exit to quit.[/yellow]")
            continue
        except Exception as e:
            _handle_error(e, fatal=False)
            continue


def _handle_error(error, fatal=True):
    """Handle errors with appropriate user-facing messages."""
    from knowsql.llm.errors import LLMAuthError, LLMRateLimitError, LLMContextError, LLMError

    if isinstance(error, LLMAuthError):
        console.print(f"[red]Authentication error:[/red] {error}")
        console.print("[dim]Check your API key environment variable.[/dim]")
    elif isinstance(error, LLMRateLimitError):
        console.print(f"[red]Rate limit exceeded:[/red] {error}")
        console.print("[dim]Wait a moment and try again.[/dim]")
    elif isinstance(error, LLMContextError):
        console.print(f"[red]Context window exceeded:[/red] {error}")
        console.print("[dim]Try a simpler question or reduce the index scope.[/dim]")
    elif isinstance(error, LLMError):
        console.print(f"[red]LLM error:[/red] {error}")
    else:
        console.print(f"[red]Error:[/red] {error}")
        logging.getLogger(__name__).debug("Full traceback:", exc_info=True)

    if fatal:
        sys.exit(1)
