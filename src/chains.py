"""
5 canonical chain nodes - one per intent.

Each chain:
1. Executes the deterministic tool(s) in the documented order.
2. Records tool calls in state["tool_results"] for observability.
3. Stores structured output in state["chain_output"].

Deterministic response formatting happens in format_response (graph.py).
LLM explanation is optional (USE_LLM_FORMATTING env flag).
"""

from __future__ import annotations

import time
from typing import Any

from langgraph.types import Command

from src.data import resolve_product, find_alternatives, get_product_by_id
from src.tools import hot_picks, compliance_filter, stock_by_warehouse, vendor_validate, kb_search
from src.models import VendorSubmission
from src._registry import get_tracer as _get_tracer_by_id


def _record(name: str, args: dict, result: Any, start: float, request_id: str = "") -> dict:
    elapsed_ms = round((time.monotonic() - start) * 1000, 2)
    record = {
        "name": name,
        "args": args,
        "result": result,
        "latency_ms": elapsed_ms,
    }
    # Also log to tracer if available
    if request_id:
        tracer = _get_tracer_by_id(request_id)
        if tracer:
            from src.observability import ToolCallRecord
            tracer._tool_records.append(ToolCallRecord(
                name=name,
                args=args,
                latency_ms=elapsed_ms,
                result_summary=str(result)[:200],
            ))
    return record


# ---------------------------------------------------------------------------
# Chain A - SALES_RECO
# hot_picks -> compliance_filter -> ranked list (blocked excluded, review flagged)
# ---------------------------------------------------------------------------

def sales_chain(state: dict[str, Any]) -> Command:
    rid = state.get("request_id", "")
    params = state.get("extracted_params") or {}
    state_code = params.get("state") or _session_state(state)
    budget = params.get("budget") or _session_budget(state) or 99999.0

    # Follow-up basket action: add resolved product to basket (simulation)
    if params.get("basket_action") and params.get("resolved_product_id"):
        resolved_id = params["resolved_product_id"]
        product = get_product_by_id(resolved_id)
        qty = params.get("quantity") or 1
        if product:
            return Command(
                update={
                    "tool_results": [],
                    "chain_output": {
                        "intent": "SALES_RECO",
                        "basket_action": True,
                        "product": {
                            "product_id": product.product_id,
                            "sku": product.sku,
                            "name": product.name,
                            "price": product.price,
                        },
                        "quantity": qty,
                    },
                },
                goto="output_guard",
            )

    if not state_code:
        return Command(
            update={
                "chain_output": {"error": "State is required for product recommendations."},
                "response_text": "Please specify a US state (e.g., CA, TX) to get recommendations.",
            },
            goto="output_guard",
        )

    tool_results = list(state.get("tool_results") or [])

    # hot_picks
    t0 = time.monotonic()
    picks = hot_picks(state=state_code, budget=float(budget))
    pick_ids = [p.product_id for p in picks]
    tool_results.append(_record("hot_picks", {"state": state_code, "budget": budget}, pick_ids, t0, rid))

    if not picks:
        return Command(
            update={
                "tool_results": tool_results,
                "chain_output": {"products": [], "state": state_code, "budget": budget},
                "response_text": f"No products found in {state_code} within ${budget:,.2f}.",
            },
            goto="output_guard",
        )

    # compliance_filter
    t1 = time.monotonic()
    compliance = compliance_filter(state=state_code, product_ids=pick_ids)
    tool_results.append(_record("compliance_filter", {"state": state_code, "product_ids": pick_ids}, len(compliance), t1, rid))

    # Build enriched product list (exclude blocked, flag review)
    products_out = []
    for cr in compliance:
        if cr.status == "blocked":
            continue  # never surface blocked products in sales output
        p = get_product_by_id(cr.product_id)
        if p is None:
            continue
        products_out.append({
            "product_id": p.product_id,
            "sku": p.sku,
            "name": p.name,
            "category": p.category,
            "price": p.price,
            "popularity_score": p.popularity_score,
            "status": cr.status,
            "reason_code": cr.reason_code,
        })

    return Command(
        update={
            "tool_results": tool_results,
            "chain_output": {
                "products": products_out,
                "state": state_code,
                "budget": budget,
                "intent": "SALES_RECO",
            },
        },
        goto="output_guard",
    )


# ---------------------------------------------------------------------------
# Chain B - COMPLIANCE_CHECK
# resolve_product -> compliance_filter -> (if blocked) find_alternatives
# ---------------------------------------------------------------------------

def compliance_chain(state: dict[str, Any]) -> Command:
    rid = state.get("request_id", "")
    params = state.get("extracted_params") or {}
    state_code = params.get("state") or _session_state(state)
    sku = params.get("sku")
    product_name = params.get("product_name")

    if not state_code:
        return Command(
            update={
                "chain_output": {"error": "State is required for compliance check."},
                "response_text": "Please specify a US state to check compliance.",
            },
            goto="output_guard",
        )

    # Resolve product
    ref = sku or product_name or ""
    product = resolve_product(ref) if ref else None

    if product is None:
        return Command(
            update={
                "chain_output": {"error": f"Product not found: {ref!r}"},
                "response_text": f"Could not find product '{ref}'. Please provide a valid SKU (e.g., SKU-1003) or product name.",
            },
            goto="output_guard",
        )

    tool_results = list(state.get("tool_results") or [])

    # compliance_filter
    t0 = time.monotonic()
    compliance = compliance_filter(state=state_code, product_ids=[product.product_id])
    tool_results.append(_record(
        "compliance_filter",
        {"state": state_code, "product_ids": [product.product_id]},
        compliance[0].status if compliance else "unknown",
        t0, rid,
    ))

    result = compliance[0]
    output: dict = {
        "intent": "COMPLIANCE_CHECK",
        "state": state_code,
        "product": {
            "product_id": product.product_id,
            "sku": product.sku,
            "name": product.name,
            "category": product.category,
        },
        "status": result.status,
        "reason_code": result.reason_code,
        "alternatives": [],
    }

    # Find alternatives if blocked
    if result.status == "blocked":
        alts = find_alternatives(
            category=product.category,
            state=state_code,
            exclude_ids=[product.product_id],
        )
        output["alternatives"] = [
            {"product_id": a.product_id, "sku": a.sku, "name": a.name,
             "price": a.price, "popularity_score": a.popularity_score}
            for a in alts
        ]

    return Command(
        update={"tool_results": tool_results, "chain_output": output},
        goto="output_guard",
    )


# ---------------------------------------------------------------------------
# Chain C - VENDOR_ONBOARDING
# vendor_validate(VendorSubmission) -> checklist + status
# ---------------------------------------------------------------------------

def vendor_chain(state: dict[str, Any]) -> Command:
    rid = state.get("request_id", "")
    params = state.get("extracted_params") or {}
    raw_submission = state.get("vendor_submission") or {}

    # Build VendorSubmission from whatever was extracted
    submission = VendorSubmission(
        name=raw_submission.get("name") or params.get("product_name"),
        category=raw_submission.get("category"),
        net_wt_oz=raw_submission.get("net_wt_oz"),
        net_vol_ml=raw_submission.get("net_vol_ml"),
        nicotine_mg=raw_submission.get("nicotine_mg"),
        lab_report_attached=raw_submission.get("lab_report_attached", False),
    )

    tool_results = list(state.get("tool_results") or [])

    t0 = time.monotonic()
    validation = vendor_validate(submission)
    tool_results.append(_record(
        "vendor_validate",
        submission.model_dump(),
        validation.status,
        t0, rid,
    ))

    return Command(
        update={
            "tool_results": tool_results,
            "chain_output": {
                "intent": "VENDOR_ONBOARDING",
                "status": validation.status,
                "missing_fields": validation.missing_fields,
                "required_documents": validation.required_documents,
                "notes": validation.notes,
                "submission": submission.model_dump(),
            },
        },
        goto="output_guard",
    )


# ---------------------------------------------------------------------------
# Chain D - OPS_STOCK
# resolve_product -> stock_by_warehouse -> warehouse qty table
# ---------------------------------------------------------------------------

def ops_chain(state: dict[str, Any]) -> Command:
    rid = state.get("request_id", "")
    params = state.get("extracted_params") or {}
    sku = params.get("sku")
    product_name = params.get("product_name")

    ref = sku or product_name or ""
    product = resolve_product(ref) if ref else None

    if product is None:
        return Command(
            update={
                "chain_output": {"error": f"Product not found: {ref!r}"},
                "response_text": f"Could not find product '{ref}'. Please provide a valid SKU or name.",
            },
            goto="output_guard",
        )

    tool_results = list(state.get("tool_results") or [])

    t0 = time.monotonic()
    inv = stock_by_warehouse(product_id=product.product_id)
    tool_results.append(_record(
        "stock_by_warehouse",
        {"product_id": product.product_id},
        inv.total_qty,
        t0, rid,
    ))

    return Command(
        update={
            "tool_results": tool_results,
            "chain_output": {
                "intent": "OPS_STOCK",
                "product": {"product_id": product.product_id, "sku": product.sku, "name": product.name},
                "total_qty": inv.total_qty,
                "warehouses": [w.model_dump() for w in inv.warehouses],
            },
        },
        goto="output_guard",
    )


# ---------------------------------------------------------------------------
# Chain E - GENERAL_KB
# kb_search -> matching doc snippets
# ---------------------------------------------------------------------------

def kb_chain(state: dict[str, Any]) -> Command:
    rid = state.get("request_id", "")
    query = state.get("user_query", "")
    user_type = state.get("user_type", "")

    tool_results = list(state.get("tool_results") or [])

    t0 = time.monotonic()
    results = kb_search(query=query, user_type=user_type)
    tool_results.append(_record("kb_search", {"query": query, "user_type": user_type}, len(results), t0, rid))

    return Command(
        update={
            "tool_results": tool_results,
            "chain_output": {
                "intent": "GENERAL_KB",
                "results": [r.model_dump() for r in results],
            },
        },
        goto="output_guard",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _session_state(state: dict[str, Any]) -> str | None:
    sess = state.get("_session") or {}
    return sess.get("last_state")


def _session_budget(state: dict[str, Any]) -> float | None:
    sess = state.get("_session") or {}
    return sess.get("last_budget")
