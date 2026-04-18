"""
LangSmith tracing bootstrap.

Import this module BEFORE any LangChain/LangGraph code runs so that
os.environ is fully configured before those libraries initialise their
tracing callbacks.

Why os.environ and not configs directly?
  pydantic-settings reads .env into the Settings object but intentionally
  does NOT write those values back into os.environ.  LangChain/LangGraph
  check os.environ at trace-start time, so we must inject the values here.
"""

from __future__ import annotations

import os

from src.logging_config import logger
from src.settings import configs


def _activate() -> bool:
    """
    Inject LangSmith credentials into os.environ and activate tracing.

    Returns True if LangSmith tracing is now active.
    """
    if not configs.langsmith_api_key:
        logger.info("LangSmith tracing disabled — LANGSMITH_API_KEY not set")
        return False

    # LangChain v0.2+ accepts both LANGCHAIN_* and LANGSMITH_* prefixes.
    # Set both for maximum compatibility across library versions.
    # Tracing is force-enabled in code whenever a LangSmith API key is present.
    os.environ.update(
        {
            "LANGCHAIN_TRACING_V2": "true",
            "LANGSMITH_TRACING": "true",
            "LANGCHAIN_API_KEY": configs.langsmith_api_key,
            "LANGSMITH_API_KEY": configs.langsmith_api_key,
            "LANGCHAIN_PROJECT": configs.langsmith_project,
            "LANGSMITH_PROJECT": configs.langsmith_project,
            "LANGCHAIN_ENDPOINT": configs.langsmith_endpoint,
            "LANGSMITH_ENDPOINT": configs.langsmith_endpoint,
        }
    )

    logger.info(
        "LangSmith tracing ACTIVE — project='{}' endpoint={}",
        configs.langsmith_project,
        configs.langsmith_endpoint,
    )
    return True


# Activated once at import time — all subsequent LangGraph/LangChain
# invocations in this process will send traces to LangSmith automatically.
langsmith_active: bool = _activate()


def tag_current_run(metadata: dict, tags: list[str] | None = None) -> None:
    """
    Attach metadata and tags to the currently-active LangSmith run tree.

    Safe to call even when tracing is disabled — silently no-ops.
    Used to annotate traces with request_id, session_id, intent, etc.
    """
    if not langsmith_active:
        return
    try:
        from langsmith import get_current_run_tree  # type: ignore[import]

        rt = get_current_run_tree()
        if rt is None:
            return
        rt.add_metadata(metadata)
        if tags:
            rt.add_tags(tags)
    except Exception:
        pass  # Never let LangSmith instrumentation break a live request


__all__ = ["langsmith_active", "tag_current_run"]
