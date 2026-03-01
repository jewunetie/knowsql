"""Tests for knowsql.config."""

import yaml
import pytest

from knowsql.config import (
    KnowSQLConfig, load_config,
)


def test_defaults():
    config = KnowSQLConfig()
    assert config.llm.provider == "anthropic"
    assert config.llm.model == "claude-sonnet-4-20250514"
    assert config.llm.api_key_env == "ANTHROPIC_API_KEY"
    assert config.indexer.sample_rows == 5
    assert config.indexer.sample_mode == "full"
    assert config.agent.confirm_tables is True
    assert config.agent.max_navigation_steps == 20


def test_yaml_override(tmp_path, monkeypatch):
    config_dir = tmp_path / ".knowsql"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"
    config_file.write_text(yaml.dump({"llm": {"provider": "openai"}}))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    config = load_config()
    assert config.llm.provider == "openai"


def test_env_var_string_override(monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setenv("KNOWSQL_LLM_PROVIDER", "openai")
    config = load_config()
    assert config.llm.provider == "openai"


def test_env_var_int_override(monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setenv("KNOWSQL_INDEXER_SAMPLE_ROWS", "10")
    config = load_config()
    assert config.indexer.sample_rows == 10
    assert isinstance(config.indexer.sample_rows, int)


def test_env_var_bool_override_true(monkeypatch, tmp_path):
    """Bug #1 regression: bool env var should work without crash."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setenv("KNOWSQL_AGENT_CONFIRM_TABLES", "true")
    config = load_config()
    assert config.agent.confirm_tables is True


def test_env_var_bool_override_false(monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setenv("KNOWSQL_AGENT_CONFIRM_TABLES", "false")
    config = load_config()
    assert config.agent.confirm_tables is False


def test_env_var_bool_before_int_check(monkeypatch, tmp_path):
    """Confirm bool is checked before int (isinstance(True, int) is True in Python)."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setenv("KNOWSQL_AGENT_CONFIRM_TABLES", "1")
    config = load_config()
    # Should be True (bool), not 1 (int)
    assert config.agent.confirm_tables is True
    assert isinstance(config.agent.confirm_tables, bool)


def test_cli_flag_overrides(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    config = load_config(provider="openai")
    assert config.llm.provider == "openai"


def test_cli_provider_openai_sets_api_key_env(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    config = load_config(provider="openai")
    assert config.llm.api_key_env == "OPENAI_API_KEY"


def test_cli_provider_openai_sets_default_model(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    config = load_config(provider="openai")
    assert config.llm.model == "gpt-4o"


def test_resolution_order(tmp_path, monkeypatch):
    """YAML sets value, env overrides it, CLI flag overrides that."""
    config_dir = tmp_path / ".knowsql"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"
    config_file.write_text(yaml.dump({"llm": {"provider": "openai"}}))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setenv("KNOWSQL_LLM_PROVIDER", "anthropic")
    # CLI flag should win
    config = load_config(provider="openai")
    assert config.llm.provider == "openai"


def test_unknown_yaml_keys_ignored(tmp_path, monkeypatch):
    config_dir = tmp_path / ".knowsql"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"
    config_file.write_text(yaml.dump({"llm": {"unknown_key": "value"}, "bogus": True}))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    config = load_config()
    # Should not crash, defaults remain
    assert config.llm.provider == "anthropic"


def test_missing_yaml_file(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    config = load_config()
    assert config.llm.provider == "anthropic"


def test_config_dir_created(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    config = load_config()
    assert (tmp_path / ".knowsql").exists()
