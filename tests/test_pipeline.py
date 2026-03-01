"""Tests for knowsql.indexer.pipeline."""

import pytest

from knowsql.indexer.pipeline import run_indexing_pipeline, _mask_connection_string
from knowsql.config import KnowSQLConfig
from knowsql.llm.provider import LLMMessage


def test_mask_connection_string_with_password():
    result = _mask_connection_string("postgresql://user:secret@host/db")
    assert "secret" not in result
    assert "****" in result
    assert "user" in result


def test_mask_connection_string_no_password():
    result = _mask_connection_string("sqlite:///test.db")
    assert result == "sqlite:///test.db"


def test_mask_connection_string_complex():
    result = _mask_connection_string("postgresql://admin:p@ss!w0rd@host:5432/mydb")
    assert "p@ss!w0rd" not in result
    assert "****" in result


def test_pipeline_integration(dummy_db, mock_llm, tmp_path, monkeypatch):
    """Full pipeline runs without crash (mock LLM, skip privacy prompt)."""
    config = KnowSQLConfig()
    config.indexer.output_dir = str(tmp_path / "output")
    config.indexer.sample_mode = "schema-only"

    # We need to patch create_provider to return our mock
    from knowsql.indexer.models import DatabaseMetadata

    # First introspect to get table names for domain response
    from knowsql.indexer.introspector import introspect_database
    db_metadata = introspect_database(dummy_db)
    table_names = [t.name for t in db_metadata.tables]

    domain_response = {
        "domains": {
            "all": {
                "description": "All tables",
                "tables": table_names,
                "also_relevant_to": {},
            }
        }
    }

    text_response = LLMMessage(role="assistant", content="# Generated\n\nStub content.\n\nKeywords: test\n")
    llm = mock_llm([domain_response] + [text_response] * 80)

    monkeypatch.setattr("knowsql.indexer.pipeline.create_provider", lambda cfg: llm)

    run_indexing_pipeline(config, dummy_db, yes=True)

    from pathlib import Path
    output = Path(config.indexer.output_dir)
    assert output.exists()
    assert (output / "INDEX.md").exists()
    assert (output / "META.json").exists()


def test_pipeline_skips_sampling_none(dummy_db, mock_llm, tmp_path, monkeypatch):
    """sample_mode='none' skips sampling."""
    config = KnowSQLConfig()
    config.indexer.output_dir = str(tmp_path / "output")
    config.indexer.sample_mode = "none"

    from knowsql.indexer.introspector import introspect_database
    db_metadata = introspect_database(dummy_db)
    table_names = [t.name for t in db_metadata.tables]

    domain_response = {
        "domains": {"all": {"description": "All", "tables": table_names, "also_relevant_to": {}}}
    }
    text_response = LLMMessage(role="assistant", content="# Stub\n\nKeywords: test\n")
    llm = mock_llm([domain_response] + [text_response] * 80)

    monkeypatch.setattr("knowsql.indexer.pipeline.create_provider", lambda cfg: llm)
    run_indexing_pipeline(config, dummy_db, yes=True)

    from pathlib import Path
    assert (Path(config.indexer.output_dir) / "INDEX.md").exists()


def test_pipeline_schema_only_mode(dummy_db, mock_llm, tmp_path, monkeypatch):
    """sample_mode='schema-only' works."""
    config = KnowSQLConfig()
    config.indexer.output_dir = str(tmp_path / "output")
    config.indexer.sample_mode = "schema-only"

    from knowsql.indexer.introspector import introspect_database
    db_metadata = introspect_database(dummy_db)
    table_names = [t.name for t in db_metadata.tables]

    domain_response = {
        "domains": {"all": {"description": "All", "tables": table_names, "also_relevant_to": {}}}
    }
    text_response = LLMMessage(role="assistant", content="# Stub\n\nKeywords: test\n")
    llm = mock_llm([domain_response] + [text_response] * 80)

    monkeypatch.setattr("knowsql.indexer.pipeline.create_provider", lambda cfg: llm)
    run_indexing_pipeline(config, dummy_db, yes=True)

    from pathlib import Path
    assert (Path(config.indexer.output_dir) / "INDEX.md").exists()
