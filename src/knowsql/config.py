"""Configuration management for KnowSQL."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class LLMConfig:
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    api_key_env: str = "ANTHROPIC_API_KEY"


@dataclass
class IndexerAdvancedConfig:
    keyword_stopwords_extend: list[str] = field(default_factory=list)
    keyword_stopwords_override: list[str] | None = None


@dataclass
class IndexerConfig:
    sample_rows: int = 5
    sample_mode: str = "full"
    max_columns_for_stats: int = 50
    output_dir: str = "./schema_index"


@dataclass
class AgentConfig:
    max_navigation_steps: int = 20
    confirm_tables: bool = True
    index_dir: str = "./schema_index"


@dataclass
class KnowSQLConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    indexer: IndexerConfig = field(default_factory=IndexerConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    indexer_advanced: IndexerAdvancedConfig = field(default_factory=IndexerAdvancedConfig)


def load_config(
    provider: str | None = None,
    model: str | None = None,
    output_dir: str | None = None,
    index_dir: str | None = None,
    sample_mode: str | None = None,
) -> KnowSQLConfig:
    """Load config with resolution: defaults -> YAML -> env vars -> CLI flags."""
    import os
    from dotenv import load_dotenv

    load_dotenv()

    config = KnowSQLConfig()

    # Read YAML config
    config_dir = Path.home() / ".knowsql"
    config_file = config_dir / "config.yaml"
    if config_file.exists():
        with open(config_file) as f:
            data = yaml.safe_load(f) or {}

        if "llm" in data:
            for k, v in data["llm"].items():
                if hasattr(config.llm, k):
                    setattr(config.llm, k, v)
        if "indexer" in data:
            for k, v in data["indexer"].items():
                if hasattr(config.indexer, k):
                    setattr(config.indexer, k, v)
        if "agent" in data:
            for k, v in data["agent"].items():
                if hasattr(config.agent, k):
                    setattr(config.agent, k, v)
        if "indexer_advanced" in data:
            for k, v in data["indexer_advanced"].items():
                if hasattr(config.indexer_advanced, k):
                    setattr(config.indexer_advanced, k, v)

    # Env var overrides (KNOWSQL_LLM_PROVIDER, etc.)
    env_map = {
        "KNOWSQL_LLM_PROVIDER": ("llm", "provider"),
        "KNOWSQL_LLM_MODEL": ("llm", "model"),
        "KNOWSQL_LLM_API_KEY_ENV": ("llm", "api_key_env"),
        "KNOWSQL_INDEXER_SAMPLE_ROWS": ("indexer", "sample_rows"),
        "KNOWSQL_INDEXER_SAMPLE_MODE": ("indexer", "sample_mode"),
        "KNOWSQL_INDEXER_OUTPUT_DIR": ("indexer", "output_dir"),
        "KNOWSQL_AGENT_MAX_NAVIGATION_STEPS": ("agent", "max_navigation_steps"),
        "KNOWSQL_AGENT_CONFIRM_TABLES": ("agent", "confirm_tables"),
    }

    for env_key, (section, attr) in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            section_obj = getattr(config, section)
            current = getattr(section_obj, attr)
            if isinstance(current, bool):
                val = val.lower() in ("true", "1", "yes")
            elif isinstance(current, int):
                val = int(val)
            setattr(section_obj, attr, val)

    # CLI flag overrides
    if provider:
        config.llm.provider = provider
        if provider == "openai":
            config.llm.api_key_env = "OPENAI_API_KEY"
            if not model:
                config.llm.model = "gpt-5-mini"
    if model:
        config.llm.model = model
    if output_dir:
        config.indexer.output_dir = output_dir
    if index_dir:
        config.agent.index_dir = index_dir
    if sample_mode:
        config.indexer.sample_mode = sample_mode

    # Ensure config dir exists
    config_dir.mkdir(parents=True, exist_ok=True)

    return config
