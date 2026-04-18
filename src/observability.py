"""
Structured observability for every request.
RequestTracer is a context manager that auto-logs on exit.

Token estimation: len(text) // 4 (char-count / 4 approximation - no tiktoken dep).
Log written to console (stdout) and appended to .logs/traces.jsonl.
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional

from src.logging_config import logger
from src.models import ToolCallRecord, TraceRecord
from src.settings import configs

_LOG_DIR = Path(configs.log_dir)
_LOG_FILE = configs.trace_log_path


def _ensure_log_dir() -> None:
    _LOG_DIR.mkdir(exist_ok=True)


def estimate_tokens(text: str) -> int:
    """Rough token estimate: characters / 4."""
    return len(text) // 4


class _ToolCallContext:
    """Returned by RequestTracer.tool_call() for capturing result and timing."""

    def __init__(self, tracer: "RequestTracer", name: str, args: dict) -> None:
        self._tracer = tracer
        self._name = name
        self._args = args
        self._start = time.monotonic()
        self._result_summary = ""

    def set_result(self, result: Any) -> None:
        summary = str(result)
        self._result_summary = summary[:200] + ("..." if len(summary) > 200 else "")

    def _finish(self) -> ToolCallRecord:
        elapsed_ms = (time.monotonic() - self._start) * 1000
        return ToolCallRecord(
            name=self._name,
            args=self._args,
            latency_ms=round(elapsed_ms, 2),
            result_summary=self._result_summary,
        )


class RequestTracer:
    """
    Context manager that records a complete request trace.

    Usage:
        with RequestTracer(session_id, user_type) as tracer:
            tracer.set_intent("SALES_RECO", tier="keyword")
            with tracer.tool_call("hot_picks", {"state": "CA", "budget": 500}) as tc:
                result = hot_picks("CA", 500)
                tc.set_result(result)
            tracer.add_tokens(prompt_text, completion_text)
    """

    def __init__(self, session_id: str, user_type: str, request_id: Optional[str] = None) -> None:
        self.request_id = request_id if request_id else str(uuid.uuid4())
        self.session_id = session_id
        self.user_type = user_type
        self._intent: Optional[str] = None
        self._tier: Optional[str] = None
        self._low_confidence = False
        self._tool_contexts: list[_ToolCallContext] = []
        self._tool_records: list[ToolCallRecord] = []
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._degraded = False
        self._degraded_reason: Optional[str] = None
        self._start = time.monotonic()

    def set_intent(self, intent: str, tier: str = "keyword", low_confidence: bool = False) -> None:
        self._intent = intent
        self._tier = tier
        self._low_confidence = low_confidence

    @contextmanager
    def tool_call(self, name: str, args: dict) -> Generator[_ToolCallContext, None, None]:
        ctx = _ToolCallContext(self, name, args)
        self._tool_contexts.append(ctx)
        try:
            yield ctx
        finally:
            self._tool_records.append(ctx._finish())

    def add_tokens(self, prompt_text: str = "", completion_text: str = "") -> None:
        self._prompt_tokens += estimate_tokens(prompt_text)
        self._completion_tokens += estimate_tokens(completion_text)

    def mark_degraded(self, reason: str) -> None:
        self._degraded = True
        self._degraded_reason = reason

    def __enter__(self) -> "RequestTracer":
        logger.debug(
            "Opening request tracer request_id={} session_id={} user_type={}",
            self.request_id,
            self.session_id,
            self.user_type,
        )
        return self

    def __exit__(self, *_: Any) -> None:
        total_ms = (time.monotonic() - self._start) * 1000
        record = TraceRecord(
            request_id=self.request_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=self.session_id,
            user_type=self.user_type,
            intent=self._intent,
            classification_tier=self._tier,
            low_confidence=self._low_confidence,
            tools_called=self._tool_records,
            total_latency_ms=round(total_ms, 2),
            prompt_tokens_est=self._prompt_tokens,
            completion_tokens_est=self._completion_tokens,
            degraded=self._degraded,
            degraded_reason=self._degraded_reason,
        )
        _write_trace(record)
        logger.debug(
            "Closed request tracer request_id={} intent={} total_latency_ms={}",
            self.request_id,
            self._intent,
            round(total_ms, 2),
        )


def _write_trace(record: TraceRecord) -> None:
    _ensure_log_dir()
    data = record.model_dump()
    line = json.dumps(data, default=str)

    # Append to JSONL file
    with _LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

    logger.info(
        "Trace written request_id={} intent={} tools_called={} trace_file={}",
        record.request_id,
        record.intent,
        len(record.tools_called),
        _LOG_FILE,
    )
