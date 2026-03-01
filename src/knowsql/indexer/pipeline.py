"""Indexing pipeline orchestrator."""

import logging
import time

from knowsql.config import KnowSQLConfig
from knowsql.llm import create_provider
from knowsql.indexer.introspector import introspect_database
from knowsql.indexer.sampler import sample_tables
from knowsql.indexer.relationship_detector import detect_relationships
from knowsql.indexer.domain_clusterer import cluster_domains
from knowsql.indexer.index_generator import generate_index
from knowsql.indexer.keyword_conflict_detector import detect_keyword_conflicts
from knowsql.utils.display import (
    console, create_indexing_progress, display_privacy_warning,
)

logger = logging.getLogger(__name__)


def run_indexing_pipeline(config: KnowSQLConfig, connection_string: str, yes: bool = False):
    """Run the full indexing pipeline with progress display."""
    start_time = time.time()

    console.print(f"\n[bold]KnowSQL Indexing Pipeline[/bold]")
    console.print(f"Connection: {_mask_connection_string(connection_string)}")
    console.print(f"Output: {config.indexer.output_dir}")
    console.print(f"LLM: {config.llm.provider}/{config.llm.model}")
    console.print()

    # Step 1: Introspection
    console.print("[bold]Step 1/6:[/bold] Introspecting database schema...")
    db_metadata = introspect_database(connection_string)
    table_count = len(db_metadata.tables)
    view_count = sum(1 for t in db_metadata.tables if t.is_view)
    console.print(f"  Found {table_count} objects ({table_count - view_count} tables, {view_count} views)")

    # Step 2: Sampling
    samples = {}
    if config.indexer.sample_mode != "none":
        # Privacy warning
        if not yes:
            if config.indexer.sample_mode == "full":
                confirmed = display_privacy_warning(config.llm.provider)
                if not confirmed:
                    console.print("[yellow]Switching to schema-only mode (no row data will be sent).[/yellow]")
                    config.indexer.sample_mode = "schema-only"

        console.print(f"[bold]Step 2/6:[/bold] Sampling data ({config.indexer.sample_mode} mode)...")
        with create_indexing_progress() as progress:
            task = progress.add_task("Sampling tables...", total=table_count)

            def sample_progress(current, total, name):
                progress.update(task, completed=current, description=f"Sampling {name}...")

            samples = sample_tables(
                connection_string=connection_string,
                tables=db_metadata.tables,
                sample_rows=config.indexer.sample_rows,
                sample_mode=config.indexer.sample_mode,
                max_columns_for_stats=config.indexer.max_columns_for_stats,
                progress_callback=sample_progress,
            )
        console.print(f"  Sampled {len(samples)} tables")
    else:
        console.print("[bold]Step 2/6:[/bold] Skipping data sampling (--no-sample-data)")

    # Step 3: Relationship Detection
    console.print("[bold]Step 3/6:[/bold] Detecting relationships...")
    relationships = detect_relationships(db_metadata)
    explicit = sum(1 for r in relationships if r.type == "explicit_fk")
    inferred = sum(1 for r in relationships if r.type == "inferred")
    console.print(f"  Found {len(relationships)} relationships ({explicit} explicit, {inferred} inferred)")

    # Create LLM provider
    llm = create_provider(config.llm)

    # Step 4: Domain Clustering
    console.print("[bold]Step 4/6:[/bold] Clustering tables into domains...")
    domains = cluster_domains(db_metadata, llm)
    console.print(f"  Created {len(domains)} domains: {', '.join(d.name for d in domains)}")

    # Step 5: Index Generation
    console.print("[bold]Step 5/6:[/bold] Generating documentation...")
    with create_indexing_progress() as progress:
        total_steps = 1 + len(domains) + len(db_metadata.tables) + 2
        task = progress.add_task("Generating files...", total=total_steps)

        def gen_progress(current, total, description):
            progress.update(task, completed=current, description=description)

        stats = generate_index(
            output_dir=config.indexer.output_dir,
            db_metadata=db_metadata,
            samples=samples,
            relationships=relationships,
            domains=domains,
            llm=llm,
            progress_callback=gen_progress,
        )

    # Step 6: Keyword Conflict Detection
    console.print("[bold]Step 6/6:[/bold] Detecting keyword conflicts...")
    detect_keyword_conflicts(
        output_dir=config.indexer.output_dir,
        llm=llm,
        stopwords_extend=config.indexer_advanced.keyword_stopwords_extend,
        stopwords_override=config.indexer_advanced.keyword_stopwords_override,
    )

    # Summary
    elapsed = time.time() - start_time
    console.print()
    console.print("[bold green]Indexing complete![/bold green]")
    console.print(f"  Tables indexed: {stats['table_count']}")
    console.print(f"  Domains created: {stats['domain_count']}")
    console.print(f"  Files generated: {stats['file_count']}")
    console.print(f"  Time elapsed: {elapsed:.1f}s")
    console.print(f"  Output directory: {config.indexer.output_dir}")
    console.print()


def _mask_connection_string(conn_str: str) -> str:
    """Mask password in connection string for display."""
    import re
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", conn_str)
