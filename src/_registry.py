"""
Shared tracer registry. Avoids circular imports between graph.py and chains.py.
Not intended for direct use outside of graph.py and chains.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

# Keyed by request_id - stores active RequestTracer instances
_active_tracers: dict[str, Any] = {}


def get_tracer(request_id: str) -> Optional[Any]:
    return _active_tracers.get(request_id)


def register_tracer(request_id: str, tracer: Any) -> None:
    _active_tracers[request_id] = tracer


def unregister_tracer(request_id: str) -> None:
    _active_tracers.pop(request_id, None)
