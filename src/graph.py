"""
LangGraph StateGraph definition.

Graph flow:
    validate_user -> classify_intent -> authorize_tools
    -> {sales_chain | compliance_chain | vendor_chain | ops_chain | kb_chain}
    -> output_guard -> format_response -> log_trace -> END

    error_response -> log_trace -> END

Exactly 5 intent routes. No FOLLOW_UP intent.
In-memory session dict. LLM timeout=30 (set in router._llm_classify).
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from typing_extensions import TypedDict

from src.data import load_seed_data
from src.guardrails import validate_user, authorize_tools, output_guard
from src.chains import sales_chain, compliance_chain, vendor_chain, ops_chain, kb_chain
from src.router import detect_followup, extract_params, classify_intent, ClassificationError
from src.state import get_session, update_session
from src.observability import RequestTracer, estimate_tokens
from src._registry import get_tracer as _registry_get, register_tracer, unregister_tracer

logger = logging.getLogger(__name__)


def _get_tracer(state: dict) -> Optional[RequestTracer]:
    return _registry_get(state.get("request_id", ""))


# ---------------------------------------------------------------------------
# Typed state
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    # Request inputs
    user_query: str
    user_type: str
    session_id: str

    # Classification
    intent: Optional[str]
    extracted_params: Optional[dict]
    classification_tier: Optional[str]

    # Vendor-specific (populated by classify node if query detected as vendor submission)
    vendor_submission: Optional[dict]

    # Tool execution
    tool_results: list[dict]
    chain_output: Optional[dict]
    redacted_chain_output: Optional[dict]   # PII-stripped copy, set by output_guard

    # Guardrails
    blocked_reason: Optional[str]
    compliance_violations: list[dict]
    degraded: bool
    degraded_reason: Optional[str]

    # Response
    response_text: Optional[str]

    # Observability - request_id only; tracer lives in _active_tracers registry
    request_id: str
    _session: Optional[dict]    # session snapshot for chain helpers


# ---------------------------------------------------------------------------
# Node: classify_intent
# ---------------------------------------------------------------------------

def node_classify_intent(state: AgentState) -> Command:
    query = state["user_query"]
    session_id = state["session_id"]
    session = get_session(session_id)
    tracer = _get_tracer(state)

    # Resolve follow-up before running classification
    is_followup, last_intent = detect_followup(query, session)

    # Extract params regardless
    params = extract_params(query)

    # Inject session defaults when params are missing
    if params.state is None and session.last_state:
        params.state = session.last_state
    if params.budget is None and session.last_budget:
        params.budget = session.last_budget

    if is_followup and last_intent:
        intent_str = last_intent
        tier = "keyword"
        low_conf = False
        # Resolve ordinal reference to a product_id and embed in params
        params_dict = params.model_dump()
        params_dict["is_followup"] = True
        # Detect basket/cart action
        import re as _re
        if _re.search(r"\b(add|basket|cart)\b", query, _re.IGNORECASE):
            params_dict["basket_action"] = True
        if params.ordinal_ref is not None and session.last_product_ids:
            try:
                resolved_id = session.last_product_ids[params.ordinal_ref]
                params_dict["resolved_product_id"] = resolved_id
            except IndexError:
                # ordinal out of range - fall back to first product
                if session.last_product_ids:
                    params_dict["resolved_product_id"] = session.last_product_ids[0]
        elif session.last_product_ids:
            # "the first one" without explicit ordinal -> index 0
            params_dict["resolved_product_id"] = session.last_product_ids[0]
    else:
        # Standard classification
        try:
            classification = classify_intent(query)
            intent_str = classification.intent
            tier = classification.tier
            low_conf = classification.low_confidence
        except ClassificationError as e:
            logger.error("Classification failed: %s", e)
            return Command(
                update={
                    "blocked_reason": str(e),
                    "response_text": "I could not understand your request. Please rephrase.",
                },
                goto="error_response",
            )
        params_dict = params.model_dump()

    if tracer:
        tracer.set_intent(intent_str, tier=tier, low_confidence=low_conf)

    # Preserve existing vendor_submission from state; only clear it if empty dict was
    # not intentionally provided (empty dict {} evaluates to None via "or None")
    existing_vendor_submission = state.get("vendor_submission")

    return Command(
        update={
            "intent": intent_str,
            "extracted_params": params_dict,
            "classification_tier": tier,
            "vendor_submission": existing_vendor_submission,  # preserve as-is
            "_session": session.model_dump(),
        },
        goto="authorize_tools",
    )


# ---------------------------------------------------------------------------
# Node: format_response (deterministic first, optional LLM)
# ---------------------------------------------------------------------------

def format_response(state: AgentState) -> Command:
    chain_output = state.get("chain_output") or {}
    intent = state.get("intent", "")
    degraded = state.get("degraded", False)
    degraded_reason = state.get("degraded_reason")
    tracer = _get_tracer(state)

    text = _format_deterministic(intent, chain_output, degraded, degraded_reason)

    # Optional LLM explanation - uses redacted output so LLM never sees raw PII
    use_llm = os.environ.get("USE_LLM_FORMATTING", "false").lower() == "true"
    if use_llm and os.environ.get("OPENAI_API_KEY"):
        try:
            redacted_output = state.get("redacted_chain_output") or chain_output
            redacted_text = _format_deterministic(intent, redacted_output, degraded, degraded_reason)
            text = _format_with_llm(intent, redacted_text, tracer)
        except Exception as exc:
            logger.warning("LLM formatting failed, using deterministic output: %s", exc)

    return Command(update={"response_text": text}, goto="log_trace")


def _format_deterministic(intent: str, output: dict, degraded: bool, degraded_reason: Optional[str]) -> str:
    prefix = ""
    if degraded:
        prefix = f"[DEGRADED - {degraded_reason}]\n\n"

    if "error" in output:
        return prefix + f"Error: {output['error']}"

    if intent == "SALES_RECO":
        # Basket follow-up response
        if output.get("basket_action"):
            p = output.get("product", {})
            qty = output.get("quantity", 1)
            return (
                prefix
                + f"Added {qty}x {p.get('name', 'product')} ({p.get('sku', '')}, "
                f"${p.get('price', 0):.2f} each) to basket.\n"
                f"[Basket simulation - no Odoo cart integration in PoC. "
                f"In production, this calls Odoo sale.order.line create via XML-RPC.]"
            )

        products = output.get("products", [])
        state = output.get("state", "")
        budget = output.get("budget", 0)
        if not products:
            return prefix + f"No products found in {state} within ${budget:,.2f}."
        lines = [f"Top picks for {state} (budget: ${float(budget):,.2f}):\n"]
        for i, p in enumerate(products, 1):
            review_flag = " [REVIEW - lab report required]" if p.get("status") == "review" else ""
            lines.append(
                f"  {i}. {p['name']} ({p['sku']}) - ${p['price']:.2f} "
                f"[popularity: {p['popularity_score']:.2f}]{review_flag}"
            )
        return prefix + "\n".join(lines)

    if intent == "COMPLIANCE_CHECK":
        p = output.get("product", {})
        status = output.get("status", "")
        reason = output.get("reason_code", "")
        alts = output.get("alternatives", [])
        state = output.get("state", "")
        lines = [
            f"Compliance check for {p.get('name', '')} ({p.get('sku', '')}) in {state}:",
            f"  Status: {status.upper()}",
        ]
        if reason:
            lines.append(f"  Reason: {reason}")
        if alts:
            lines.append(f"\nAlternatives in {state} ({p.get('category', '')}):")
            for a in alts:
                lines.append(f"  - {a['name']} ({a['sku']}) - ${a['price']:.2f}")
        return prefix + "\n".join(lines)

    if intent == "VENDOR_ONBOARDING":
        status = output.get("status", "")
        missing = output.get("missing_fields", [])
        docs = output.get("required_documents", [])
        notes = output.get("notes", "")
        lines = [f"Vendor submission validation: {status}"]
        if missing:
            lines.append(f"  Missing fields: {', '.join(missing)}")
        if docs:
            lines.append(f"  Required documents: {', '.join(docs)}")
        lines.append(f"  Notes: {notes}")
        return prefix + "\n".join(lines)

    if intent == "OPS_STOCK":
        p = output.get("product", {})
        total = output.get("total_qty", 0)
        warehouses = output.get("warehouses", [])
        lines = [f"Stock for {p.get('name', '')} ({p.get('sku', '')}):", f"  Total: {total} units"]
        if warehouses:
            lines.append("  By warehouse:")
            for w in warehouses:
                lines.append(f"    {w['warehouse']}: {w['qty']} units")
        return prefix + "\n".join(lines)

    if intent == "GENERAL_KB":
        results = output.get("results", [])
        if not results:
            return prefix + "No relevant documentation found."
        lines = ["Knowledge base results:"]
        for r in results:
            lines.append(f"\n  [{r['doc_id']}] {r['title']}")
            lines.append(f"  {r['snippet']}")
        return prefix + "\n".join(lines)

    return prefix + str(output)


def _format_with_llm(intent: str, deterministic_text: str, tracer: Any) -> str:
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, timeout=30, max_tokens=500)
    prompt = (
        f"You are a helpful B2B product assistant. "
        f"Rephrase the following structured data as a clear, concise response. "
        f"Do not add any facts not present in the data.\n\n"
        f"Data:\n{deterministic_text}\n\n"
        f"Rephrased response:"
    )
    response = llm.invoke(prompt)
    content = response.content if hasattr(response, "content") else str(response)

    if tracer:
        tracer.add_tokens(prompt, content)

    return content


# ---------------------------------------------------------------------------
# Node: log_trace
# ---------------------------------------------------------------------------

def log_trace(state: AgentState) -> Command:
    return Command(goto=END)


# ---------------------------------------------------------------------------
# Node: error_response
# ---------------------------------------------------------------------------

def error_response(state: AgentState) -> Command:
    reason = state.get("blocked_reason", "Unknown error")
    text = state.get("response_text") or f"Request blocked: {reason}"
    return Command(update={"response_text": text}, goto="log_trace")


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def build_graph() -> Any:
    """Build and compile the LangGraph StateGraph."""
    load_seed_data()

    builder = StateGraph(AgentState)

    builder.add_node("validate_user", validate_user)
    builder.add_node("classify_intent", node_classify_intent)
    builder.add_node("authorize_tools", authorize_tools)
    builder.add_node("sales_chain", sales_chain)
    builder.add_node("compliance_chain", compliance_chain)
    builder.add_node("vendor_chain", vendor_chain)
    builder.add_node("ops_chain", ops_chain)
    builder.add_node("kb_chain", kb_chain)
    builder.add_node("output_guard", output_guard)
    builder.add_node("format_response", format_response)
    builder.add_node("log_trace", log_trace)
    builder.add_node("error_response", error_response)

    builder.add_edge(START, "validate_user")

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# run_query - main entry point for a single turn
# ---------------------------------------------------------------------------

def run_query(
    graph: Any,
    user_query: str,
    user_type: str,
    session_id: str,
    vendor_submission: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Execute one chat turn through the graph.
    Returns a dict with at minimum 'response_text', 'intent', 'request_id'.
    """
    request_id = str(uuid.uuid4())

    with RequestTracer(session_id=session_id, user_type=user_type, request_id=request_id) as tracer:
        # Register tracer so graph nodes can access it without putting a
        # non-serializable object into LangGraph checkpointed state.
        register_tracer(request_id, tracer)

        try:
            initial_state: AgentState = {
                "user_query": user_query,
                "user_type": user_type,
                "session_id": session_id,
                "intent": None,
                "extracted_params": None,
                "classification_tier": None,
                "vendor_submission": vendor_submission,
                "tool_results": [],
                "chain_output": None,
                "redacted_chain_output": None,
                "blocked_reason": None,
                "compliance_violations": [],
                "degraded": False,
                "degraded_reason": None,
                "response_text": None,
                "request_id": request_id,
                "_session": None,
            }

            config = {"configurable": {"thread_id": session_id}}
            final_state = graph.invoke(initial_state, config=config)

            # Update session state from results
            intent = final_state.get("intent") or ""
            params = final_state.get("extracted_params") or {}
            chain_output = final_state.get("chain_output") or {}

            # Only SALES_RECO produces a selectable product list for follow-ups.
            # Compliance/ops/vendor/kb turns must NOT overwrite last_intent or
            # last_product_ids - that would corrupt Q5 basket resolution.
            product_ids: list[int] = []
            if intent == "SALES_RECO":
                product_ids = [p["product_id"] for p in chain_output.get("products", [])]

            update_session(
                session_id,
                intent=intent if intent == "SALES_RECO" else "",
                state=params.get("state"),
                budget=params.get("budget"),
                product_ids=product_ids if product_ids else None,
            )

            # Token estimate from full request/response text
            tracer.add_tokens(user_query, final_state.get("response_text") or "")

        finally:
            unregister_tracer(request_id)

    return {
        "request_id": request_id,
        "intent": intent,
        "response_text": final_state.get("response_text") or "",
        "degraded": final_state.get("degraded", False),
        "classification_tier": final_state.get("classification_tier"),
        "tool_results": final_state.get("tool_results", []),
    }
