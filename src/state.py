"""
Minimal in-memory session state.
Stores exactly the 4 fields required by the problem statement.
Keyed by session_id (str -> SessionState).
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class SessionState(BaseModel):
    last_intent: str = ""                    # one of 5 valid intents
    last_state: Optional[str] = None         # US state code
    last_budget: Optional[float] = None
    last_product_ids: list[int] = Field(default_factory=list)


# Module-level store - lives for the process lifetime
_sessions: dict[str, SessionState] = {}


def get_session(session_id: str) -> SessionState:
    """Return existing session or create a new empty one."""
    if session_id not in _sessions:
        _sessions[session_id] = SessionState()
    return _sessions[session_id]


def update_session(
    session_id: str,
    intent: str = "",
    state: Optional[str] = None,
    budget: Optional[float] = None,
    product_ids: Optional[list[int]] = None,
) -> None:
    """Merge new values into the session. None values leave existing field unchanged."""
    sess = get_session(session_id)
    if intent:
        sess.last_intent = intent
    if state is not None:
        sess.last_state = state
    if budget is not None:
        sess.last_budget = budget
    if product_ids is not None:
        sess.last_product_ids = product_ids
