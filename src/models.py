"""
Pydantic models for all data types and tool I/O schemas.
All business rule configurations (VENDOR_POLICY) live here as declared constants.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Seed data models
# ---------------------------------------------------------------------------


class ProductFlags(BaseModel):
    nicotine: bool = False
    thc: bool = False
    cbd: bool = False
    kratom: bool = False
    mushroom: bool = False


class Product(BaseModel):
    product_id: int
    sku: str
    name: str
    category: str
    flags: ProductFlags
    blocked_states: list[str] = Field(default_factory=list)
    lab_report_required: bool = False
    price: float
    popularity_score: float


class InventoryEntry(BaseModel):
    product_id: int
    warehouse: str
    qty: int


class Customer(BaseModel):
    customer_id: int
    name: str
    state: str
    tier: str


class Vendor(BaseModel):
    vendor_id: int
    name: str


class KBDoc(BaseModel):
    doc_id: str
    title: str
    visibility: Literal["internal", "public", "vendor"]
    text: str


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

VALID_INTENTS = {
    "SALES_RECO",
    "COMPLIANCE_CHECK",
    "VENDOR_ONBOARDING",
    "OPS_STOCK",
    "GENERAL_KB",
}
VALID_USER_TYPES = {"internal_sales", "portal_vendor", "portal_customer"}


class IntentClassification(BaseModel):
    intent: Literal[
        "SALES_RECO", "COMPLIANCE_CHECK", "VENDOR_ONBOARDING", "OPS_STOCK", "GENERAL_KB"
    ]
    confidence: float = 1.0
    tier: Literal["keyword", "llm"] = "keyword"
    low_confidence: bool = False


class ExtractedParams(BaseModel):
    state: str | None = None
    budget: float | None = None
    sku: str | None = None
    product_name: str | None = None
    quantity: int | None = None
    ordinal_ref: int | None = None  # 0-indexed: "first one" -> 0


# ---------------------------------------------------------------------------
# Tool I/O schemas
# ---------------------------------------------------------------------------


class ComplianceResult(BaseModel):
    product_id: int
    sku: str
    name: str
    status: Literal["allowed", "blocked", "review"]
    reason_code: str


class InventoryResult(BaseModel):
    product_id: int
    sku: str
    name: str
    warehouses: list[InventoryEntry]
    total_qty: int


class VendorSubmission(BaseModel):
    """Vendor product submission for validation. All fields optional - missing = fail."""

    name: str | None = None
    category: str | None = None
    net_wt_oz: float | None = None
    net_vol_ml: float | None = None
    nicotine_mg: float | None = None
    lab_report_attached: bool = False


class VendorValidationResult(BaseModel):
    status: Literal["PASS", "REVIEW", "FAIL"]
    missing_fields: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    notes: str = ""


class KBSearchResult(BaseModel):
    doc_id: str
    title: str
    snippet: str
    visibility: str
    score: int


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------


class ToolCallRecord(BaseModel):
    name: str
    args: dict
    latency_ms: float
    result_summary: str = ""


class TraceRecord(BaseModel):
    request_id: str
    timestamp: str
    session_id: str
    user_type: str
    intent: str | None = None
    classification_tier: str | None = None
    low_confidence: bool = False
    tools_called: list[ToolCallRecord] = Field(default_factory=list)
    total_latency_ms: float = 0.0
    prompt_tokens_est: int = 0
    completion_tokens_est: int = 0
    degraded: bool = False
    degraded_reason: str | None = None


# ---------------------------------------------------------------------------
# Business rules - declared policy (NOT inferred from seed data)
# ---------------------------------------------------------------------------

VENDOR_POLICY: dict = {
    # Fields every vendor product submission must have
    "required_fields": ["name", "category", "net_wt_oz", "net_vol_ml"],
    # Categories that require an attached lab report for new submissions.
    # This is a declared business rule. The seed data has mixed lab_report_required
    # within these categories because it reflects historical products, not new submissions.
    "lab_report_categories": ["THC Beverage", "Mushroom Gummies"],
}

# Tool allowlists per user_type
TOOL_ALLOWLIST: dict[str, set[str]] = {
    "internal_sales": {
        "hot_picks",
        "compliance_filter",
        "stock_by_warehouse",
        "vendor_validate",
        "kb_search",
    },
    "portal_vendor": {"vendor_validate", "kb_search"},
    "portal_customer": {
        "hot_picks",
        "compliance_filter",
        "stock_by_warehouse",
        "kb_search",
    },
}

# Tools required per intent
INTENT_TOOLS: dict[str, set[str]] = {
    "SALES_RECO": {"hot_picks", "compliance_filter"},
    "COMPLIANCE_CHECK": {"compliance_filter"},
    "VENDOR_ONBOARDING": {"vendor_validate"},
    "OPS_STOCK": {"stock_by_warehouse"},
    "GENERAL_KB": {"kb_search"},
}

# KB doc visibility access per user_type
KB_VISIBILITY: dict[str, set[str]] = {
    "internal_sales": {"internal", "public", "vendor"},
    "portal_vendor": {"vendor", "public"},
    "portal_customer": {"public"},
}
