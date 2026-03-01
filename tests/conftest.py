"""Shared test fixtures for KnowSQL test suite."""

import json
import sqlite3

import pytest

from knowsql.llm.provider import LLMProvider, LLMMessage


class MockLLMProvider(LLMProvider):
    """Fake LLM provider that returns pre-configured responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []  # list of (method, messages, kwargs)

    def complete(self, messages, tools=None, temperature=0.0):
        self.calls.append(("complete", messages, {"tools": tools}))
        resp = self.responses.pop(0)
        if isinstance(resp, LLMMessage):
            return resp
        # Allow passing raw string as shorthand
        return LLMMessage(role="assistant", content=str(resp))

    def complete_json(self, messages, temperature=0.0):
        self.calls.append(("complete_json", messages, {}))
        return self.responses.pop(0)


@pytest.fixture
def mock_llm():
    """Factory fixture that creates MockLLMProvider with given responses."""
    def _factory(responses):
        return MockLLMProvider(responses)
    return _factory


@pytest.fixture(scope="session")
def dummy_db(tmp_path_factory):
    """Create the dummy e-commerce SQLite database. Returns connection string."""
    import sys
    import os
    # Import from scripts
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    from generate_dummy_db import create_tables, populate_data

    db_dir = tmp_path_factory.mktemp("db")
    db_path = db_dir / "dummy_ecommerce.db"

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    create_tables(conn)
    populate_data(conn)
    conn.close()

    return f"sqlite:///{db_path}"


@pytest.fixture(scope="session")
def db_metadata(dummy_db):
    """Introspect the dummy database and return DatabaseMetadata."""
    from knowsql.indexer.introspector import introspect_database
    return introspect_database(dummy_db)


@pytest.fixture
def sample_index_dir(tmp_path):
    """Create a minimal pre-built index directory for navigator/agent tests."""
    root = tmp_path / "schema_index"
    root.mkdir()

    # META.json
    (root / "META.json").write_text(json.dumps({
        "dialect": "sqlite",
        "schemas": [],
        "table_count": 2,
    }))

    # INDEX.md
    (root / "INDEX.md").write_text(
        "# Database Index\n\n"
        "This is a SQLite e-commerce database.\n\n"
        "## Domains\n\n"
        "- sales: Orders and transactions\n"
        "- customers: Customer data\n"
    )

    # domains/sales
    sales_dir = root / "domains" / "sales"
    tables_dir = sales_dir / "tables"
    tables_dir.mkdir(parents=True)

    (sales_dir / "DOMAIN.md").write_text(
        "# Sales Domain\n\nHandles orders and transactions.\n\n"
        "## Tables\n\n- orders\n- customers\n"
    )

    (tables_dir / "orders.md").write_text(
        "# orders\n\nContains customer orders.\n\n"
        "Keywords: purchases, transactions, sales\n\n"
        "## Columns\n\n"
        "### id\n- Type: INTEGER\n- Primary Key\n"
        "Keywords: order id, order number\n\n"
        "### customer_id\n- Type: INTEGER\n"
        "Keywords: buyer, purchaser\n\n"
        "### total_amount\n- Type: REAL\n"
        "Keywords: order total, price\n\n"
        "## Relationships\n\n"
        "- orders.customer_id -> customers.id (explicit_fk, one-to-many)\n"
    )

    (tables_dir / "customers.md").write_text(
        "# customers\n\nContains customer records.\n\n"
        "Keywords: buyers, clients, users\n\n"
        "## Columns\n\n"
        "### id\n- Type: INTEGER\n- Primary Key\n"
        "Keywords: customer id\n\n"
        "### email\n- Type: TEXT\n"
        "Keywords: email address, contact\n\n"
        "## Relationships\n\n"
        "- orders.customer_id -> customers.id\n"
    )

    # cross_references
    xref_dir = root / "cross_references"
    xref_dir.mkdir()

    (xref_dir / "RELATIONSHIPS.md").write_text(
        "# Relationships\n\n"
        "- orders.customer_id -> customers.id (explicit_fk, one-to-many) [sales -> sales]\n"
    )

    (xref_dir / "GLOSSARY.md").write_text(
        "# Glossary\n\n- customer -> customers table\n- order -> orders table\n"
    )

    (xref_dir / "AMBIGUOUS_TERMS.md").write_text(
        "# Ambiguous Terms\n\nNo ambiguous terms detected.\n"
    )

    return root
