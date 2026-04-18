"""
5 deterministic tools. All operate on in-memory data from src/data.py.
No LLM inside any tool. Pydantic validates all inputs.
These are the only functions logged in observability tool_calls and checked in allowlists.

Each tool is decorated with @traceable so LangSmith captures inputs, outputs,
and latency as child spans under the active LangGraph trace.
"""

from __future__ import annotations

from langsmith import traceable  # type: ignore[import]

from src.data import (
    get_inventory,
    get_kb_docs,
    get_product_by_id,
    get_products,
)
from src.models import (
    KB_VISIBILITY,
    VENDOR_POLICY,
    ComplianceResult,
    InventoryResult,
    KBSearchResult,
    Product,
    VendorSubmission,
    VendorValidationResult,
)

# ---------------------------------------------------------------------------
# Tool 1 - hot_picks
# ---------------------------------------------------------------------------


@traceable(run_type="tool", name="hot_picks")
def hot_picks(state: str, budget: float, limit: int = 10) -> list[Product]:
    """
    Return products ranked by popularity_score (desc) that are:
    - priced at or below budget
    - not blocked in the given state

    Args:
        state:  Two-letter US state code (e.g. "CA").
        budget: Maximum price.
        limit:  Max results to return.
    """
    candidates = [p for p in get_products() if p.price <= budget and state not in p.blocked_states]
    candidates.sort(key=lambda p: p.popularity_score, reverse=True)
    return candidates[:limit]


# ---------------------------------------------------------------------------
# Tool 2 - compliance_filter
# ---------------------------------------------------------------------------


@traceable(run_type="tool", name="compliance_filter")
def compliance_filter(state: str, product_ids: list[int]) -> list[ComplianceResult]:
    """
    Deterministic three-way compliance check for each product in a given state.

    Status rules (in priority order):
        blocked - state is in product.blocked_states
        review  - product is not blocked but lab_report_required == True
        allowed - neither blocked nor requires lab report

    Args:
        state:       Two-letter US state code.
        product_ids: List of product_id integers to check.
    """
    results: list[ComplianceResult] = []

    for pid in product_ids:
        product = get_product_by_id(pid)
        if product is None:
            # Unknown product - treat as review (cannot confirm compliance)
            results.append(
                ComplianceResult(
                    product_id=pid,
                    sku="UNKNOWN",
                    name="Unknown Product",
                    status="review",
                    reason_code=(
                        f"Product ID {pid} not found in catalog - compliance cannot be confirmed"
                    ),
                )
            )
            continue

        if state in product.blocked_states:
            active_flags = [
                f
                for f in ["nicotine", "thc", "cbd", "kratom", "mushroom"]
                if getattr(product.flags, f)
            ]
            flag_str = ", ".join(active_flags) if active_flags else "regulated"
            results.append(
                ComplianceResult(
                    product_id=pid,
                    sku=product.sku,
                    name=product.name,
                    status="blocked",
                    reason_code=f"{flag_str} product blocked in {state} per state regulation",
                )
            )

        elif product.lab_report_required:
            results.append(
                ComplianceResult(
                    product_id=pid,
                    sku=product.sku,
                    name=product.name,
                    status="review",
                    reason_code="Lab report required - pending verification before sale",
                )
            )

        else:
            results.append(
                ComplianceResult(
                    product_id=pid,
                    sku=product.sku,
                    name=product.name,
                    status="allowed",
                    reason_code="",
                )
            )

    return results


# ---------------------------------------------------------------------------
# Tool 3 - stock_by_warehouse
# ---------------------------------------------------------------------------


@traceable(run_type="tool", name="stock_by_warehouse")
def stock_by_warehouse(product_id: int) -> InventoryResult:
    """
    Return warehouse breakdown for a product.

    Args:
        product_id: Integer product ID.
    """
    product = get_product_by_id(product_id)
    warehouses = [e for e in get_inventory() if e.product_id == product_id]
    total = sum(e.qty for e in warehouses)

    return InventoryResult(
        product_id=product_id,
        sku=product.sku if product else "UNKNOWN",
        name=product.name if product else f"Product {product_id}",
        warehouses=warehouses,
        total_qty=total,
    )


# ---------------------------------------------------------------------------
# Tool 4 - vendor_validate
# ---------------------------------------------------------------------------


@traceable(run_type="tool", name="vendor_validate")
def vendor_validate(submission: VendorSubmission) -> VendorValidationResult:
    """
    Validate a vendor product submission against VENDOR_POLICY rules.

    Status:
        PASS   - all required fields present, all docs attached
        REVIEW - all required fields present, but a required document is missing
        FAIL   - one or more required fields are missing

    Args:
        submission: VendorSubmission Pydantic model (types validated on construction).
    """
    missing_fields: list[str] = []
    required_docs: list[str] = []

    # Check required data fields
    for field in VENDOR_POLICY["required_fields"]:
        value = getattr(submission, field, None)
        if value is None:
            missing_fields.append(field)

    # Check lab report requirement (declared policy - not inferred from seed data)
    if (
        submission.category in VENDOR_POLICY["lab_report_categories"]
        and not submission.lab_report_attached
    ):
        required_docs.append("lab_report")

    if missing_fields:
        return VendorValidationResult(
            status="FAIL",
            missing_fields=missing_fields,
            required_documents=required_docs,
            notes=f"Missing required fields: {', '.join(missing_fields)}",
        )

    if required_docs:
        return VendorValidationResult(
            status="REVIEW",
            missing_fields=[],
            required_documents=required_docs,
            notes=f"Required documents missing: {', '.join(required_docs)}",
        )

    return VendorValidationResult(
        status="PASS",
        missing_fields=[],
        required_documents=[],
        notes="All required fields and documents are present",
    )


# ---------------------------------------------------------------------------
# Tool 5 - kb_search
# ---------------------------------------------------------------------------


@traceable(run_type="tool", name="kb_search")
def kb_search(query: str, user_type: str, top_k: int = 3) -> list[KBSearchResult]:
    """
    Naive keyword-overlap search over kb_docs, filtered by user_type visibility.

    Args:
        query:     User query string.
        user_type: One of internal_sales, portal_vendor, portal_customer.
        top_k:     Max results to return.
    """
    visible = KB_VISIBILITY.get(user_type, {"public"})
    query_tokens = set(query.lower().split())

    scored: list[tuple[int, KBSearchResult]] = []

    for doc in get_kb_docs():
        if doc.visibility not in visible:
            continue

        doc_tokens = set((doc.title + " " + doc.text).lower().split())
        score = len(query_tokens & doc_tokens)

        # Always include all visible docs, even with score 0 (short kb)
        snippet = doc.text[:200] + ("..." if len(doc.text) > 200 else "")
        scored.append(
            (
                score,
                KBSearchResult(
                    doc_id=doc.doc_id,
                    title=doc.title,
                    snippet=snippet,
                    visibility=doc.visibility,
                    score=score,
                ),
            )
        )

    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:top_k]]
