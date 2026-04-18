"""
Three guardrail functions used as LangGraph nodes.

validate_user   - pre-classify: validates user_type enum only
authorize_tools - post-classify: checks intent tools vs user_type allowlist
output_guard    - post-chain: asserts no blocked products leaked into response
"""

from __future__ import annotations

import copy
from typing import Any

from langgraph.types import Command

from src.logging_config import logger
from src.models import TOOL_ALLOWLIST, INTENT_TOOLS, VALID_USER_TYPES

# Fields considered PII in chain output dicts
_PII_KEYS = {"name", "customer_id", "vendor_id", "email", "phone", "address"}


def redact_for_llm(chain_output: dict) -> dict:
    """
    Remove PII fields from chain output before passing to an LLM.

    Operates on the vendor submission sub-dict and any top-level entity IDs.
    Returns a new dict; does not mutate the original.

    Kept fields:
    - Product names are preserved ("name" only redacted inside submission).
    - Structural fields (status, missing_fields, etc.) are always preserved.
    """
    out = copy.deepcopy(chain_output)
    if "submission" in out and isinstance(out["submission"], dict):
        for key in _PII_KEYS:
            out["submission"].pop(key, None)
    # Redact entity-level IDs at the top level but keep product names
    for key in _PII_KEYS - {"name"}:
        out.pop(key, None)
    return out


def validate_user(state: dict[str, Any]) -> Command:
    """
    Validate that user_type is a recognized enum value.
    Does NOT check intent (not yet classified).
    """
    user_type = state.get("user_type", "")
    if user_type not in VALID_USER_TYPES:
        return Command(
            update={
                "blocked_reason": f"Invalid user_type: {user_type!r}. "
                                  f"Must be one of: {sorted(VALID_USER_TYPES)}",
                "response_text": f"Access denied: unknown user type '{user_type}'.",
            },
            goto="error_response",
        )
    return Command(goto="classify_intent")


def authorize_tools(state: dict[str, Any]) -> Command:
    """
    Post-classify: verify the resolved intent's required tools are all
    in the user_type's allowlist.
    """
    user_type = state.get("user_type", "")
    intent = state.get("intent", "")

    required_tools = INTENT_TOOLS.get(intent, set())
    allowed_tools = TOOL_ALLOWLIST.get(user_type, set())

    denied = required_tools - allowed_tools
    if denied:
        reason = (
            f"{user_type} cannot access tool(s) {sorted(denied)} "
            f"required by intent {intent}"
        )
        logger.warning("Tool authorization denied: {}", reason)
        return Command(
            update={
                "blocked_reason": reason,
                "response_text": f"Access denied: {reason}.",
            },
            goto="error_response",
        )

    # Route to the appropriate chain node
    chain_map = {
        "SALES_RECO":        "sales_chain",
        "COMPLIANCE_CHECK":  "compliance_chain",
        "VENDOR_ONBOARDING": "vendor_chain",
        "OPS_STOCK":         "ops_chain",
        "GENERAL_KB":        "kb_chain",
    }
    next_node = chain_map.get(intent, "error_response")
    return Command(goto=next_node)


def output_guard(state: dict[str, Any]) -> Command:
    """
    Assert no blocked products survived the chain.

    If any blocked product is found in chain_output, this is a compliance
    assertion failure - NOT silent filtering. The request is marked degraded
    and logged at ERROR.

    PII redaction runs here: redact_for_llm() strips vendor/customer entity
    identifiers before any LLM formatting step can see them.
    """
    chain_output = state.get("chain_output") or {}
    products = chain_output.get("products", [])

    redacted = redact_for_llm(chain_output)

    blocked_leaks = [p for p in products if p.get("status") == "blocked"]

    if blocked_leaks:
        ids = [p.get("product_id") for p in blocked_leaks]
        reason = f"COMPLIANCE ASSERTION FAILURE: blocked products {ids} leaked into response"
        logger.error(reason)
        return Command(
            update={
                "degraded": True,
                "degraded_reason": reason,
                "redacted_chain_output": redacted,
            },
            goto="format_response",
        )

    return Command(update={"redacted_chain_output": redacted}, goto="format_response")
