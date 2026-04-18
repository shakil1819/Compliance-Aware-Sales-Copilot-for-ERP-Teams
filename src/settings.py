"""
Centralized application settings.

Import `configs` and read attributes directly:
    from src.settings import configs
    configs.openai_api_key
    configs.use_llm_formatting
"""

from __future__ import annotations

from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ai-chat-service-poc"
    environment: str = "development"

    openai_api_key: str | None = None
    use_llm_formatting: bool = False

    # LangSmith observability — all optional, system works without them
    langsmith_api_key: str | None = None
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_tracing: bool = False
    langsmith_project: str = "ai-chat-service-poc"

    log_level: str = "INFO"
    log_dir: str = ".logs"
    log_file: str = "application.log"
    trace_log_file: str = "traces.jsonl"
    log_rotation: str = "5 MB"
    log_retention: str = "10 days"
    log_enqueue: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def log_path(self) -> Path:
        return Path(self.log_dir) / self.log_file

    @computed_field  # type: ignore[prop-decorator]
    @property
    def trace_log_path(self) -> Path:
        return Path(self.log_dir) / self.trace_log_file


configs = Settings()

