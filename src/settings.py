"""
Centralized application settings.

Import `configs` and read attributes directly:
    from src.settings import configs
    configs.openai_api_key
    configs.use_llm_formatting

Configuration is merged from (highest priority first): constructor kwargs, environment
variables, `.env`, optional `config.toml`, then Docker/K8s-style secret files.

TOML may use flat keys matching field names (e.g. openai_api_key) or nested tables
whose keys join with underscores (e.g. [openai] / api_key -> openai_api_key).
Environment variables and `.env` override values from `config.toml`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import computed_field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources import InitSettingsSource, TomlConfigSettingsSource
from pydantic_settings.sources.types import DEFAULT_PATH, PathType

# Nested [features] / use_llm_formatting -> features_use_llm_formatting; map to the real field.
_TOML_FLAT_KEY_ALIASES: dict[str, str] = {
    "features_use_llm_formatting": "use_llm_formatting",
}


def _flatten_toml_tables(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Turn nested TOML tables into flat snake_case keys matching Settings fields."""
    out: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            sub_prefix = f"{prefix}{key}_" if prefix else f"{key}_"
            out.update(_flatten_toml_tables(value, sub_prefix))
        else:
            flat_key = f"{prefix}{key}" if prefix else key
            if isinstance(flat_key, str) and flat_key.isupper() and "_" in flat_key:
                flat_key = flat_key.lower()
            out[flat_key] = value
    for old, new in _TOML_FLAT_KEY_ALIASES.items():
        if old in out and new not in out:
            out[new] = out.pop(old)
    return out


class FlatteningTomlConfigSettingsSource(TomlConfigSettingsSource):
    """
    Like TomlConfigSettingsSource, but flattens nested TOML tables so [openai] / api_key
    maps to field openai_api_key.
    """

    def __init__(
        self,
        settings_cls: type[BaseSettings],
        toml_file: PathType | None = DEFAULT_PATH,
        deep_merge: bool = False,
    ) -> None:
        self.toml_file_path = (
            toml_file if toml_file != DEFAULT_PATH else settings_cls.model_config.get("toml_file")
        )
        if os.environ.get("SETTINGS_TOML"):
            self.toml_file_path = os.environ["SETTINGS_TOML"]
        raw = self._read_files(self.toml_file_path, deep_merge=deep_merge)
        self.toml_data = _flatten_toml_tables(raw)
        InitSettingsSource.__init__(self, settings_cls, self.toml_data)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        toml_file=Path("config.toml"),
    )

    app_name: str = "ai-chat-service-poc"
    environment: str = "development"

    openai_api_key: str | None = None
    use_llm_formatting: bool = False

    # LangSmith observability — all optional, system works without them
    langsmith_api_key: str | None = None
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_tracing: bool = True
    langsmith_project: str = "ai-chat-service-poc"

    log_level: str = "INFO"
    log_dir: str = ".logs"
    log_file: str = "application.log"
    trace_log_file: str = "traces.jsonl"
    log_rotation: str = "5 MB"
    log_retention: str = "10 days"
    log_enqueue: bool = False

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            FlatteningTomlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def log_path(self) -> Path:
        return Path(self.log_dir) / self.log_file

    @computed_field  # type: ignore[prop-decorator]
    @property
    def trace_log_path(self) -> Path:
        return Path(self.log_dir) / self.trace_log_file


configs = Settings()
