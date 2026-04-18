"""
AI Chat Service PoC - src package public API.

Layer structure (import order matters - no circular deps):
  models       -> no internal imports
  data         -> models
  tools        -> data, models
  state        -> models
  router       -> models, state
  guardrails   -> models
  observability -> models
  chains       -> data, tools, models, _registry
  graph        -> all of the above

External callers only need: build_graph, run_query, load_seed_data.
The rest is exported for testing and introspection.
"""

# ---------------------------------------------------------------------------
# Data schemas (Pydantic models + policy constants)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Chain nodes (one per intent)
# ---------------------------------------------------------------------------
from src.chains import (
    compliance_chain,
    kb_chain,
    ops_chain,
    sales_chain,
    vendor_chain,
)

# ---------------------------------------------------------------------------
# Data layer (in-memory seed data + lookup helpers)
# ---------------------------------------------------------------------------
from src.data import (
    find_alternatives,
    get_customers,
    get_inventory,
    get_kb_docs,
    get_product_by_id,
    get_product_by_sku,
    get_products,
    get_vendors,
    load_seed_data,
    # Chain helpers (not tools - not in allowlists)
    resolve_product,
)

# ---------------------------------------------------------------------------
# Graph orchestration (primary external API)
# ---------------------------------------------------------------------------
from src.graph import (
    AgentState,
    build_graph,
    run_query,
)

# ---------------------------------------------------------------------------
# Guardrail nodes
# ---------------------------------------------------------------------------
from src.guardrails import (
    authorize_tools,
    output_guard,
    validate_user,
)
from src.models import (
    INTENT_TOOLS,
    KB_VISIBILITY,
    TOOL_ALLOWLIST,
    VALID_INTENTS,
    VALID_USER_TYPES,
    # Business rule configs
    VENDOR_POLICY,
    ComplianceResult,
    Customer,
    ExtractedParams,
    # Tool I/O schemas
    IntentClassification,
    InventoryEntry,
    InventoryResult,
    KBDoc,
    KBSearchResult,
    Product,
    # Seed data types
    ProductFlags,
    # Observability schemas
    ToolCallRecord,
    TraceRecord,
    Vendor,
    VendorSubmission,
    VendorValidationResult,
)

# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------
from src.observability import (
    RequestTracer,
    estimate_tokens,
)

# ---------------------------------------------------------------------------
# Intent classification (3 decomposed functions)
# ---------------------------------------------------------------------------
from src.router import (
    US_STATES,
    ClassificationError,
    classify_intent,
    detect_followup,
    extract_params,
)

# ---------------------------------------------------------------------------
# Session state (in-memory, 4-field minimum)
# ---------------------------------------------------------------------------
from src.state import (
    SessionState,
    get_session,
    update_session,
)

# ---------------------------------------------------------------------------
# Deterministic tools (5 canonical tools, no LLM)
# ---------------------------------------------------------------------------
from src.tools import (
    compliance_filter,
    hot_picks,
    kb_search,
    stock_by_warehouse,
    vendor_validate,
)

# ---------------------------------------------------------------------------
# Explicit public API
# ---------------------------------------------------------------------------
__all__ = [
    # --- Entry points ---
    "build_graph",
    "run_query",
    "load_seed_data",
    # --- Pydantic models ---
    "ProductFlags",
    "Product",
    "InventoryEntry",
    "Customer",
    "Vendor",
    "KBDoc",
    "IntentClassification",
    "ExtractedParams",
    "ComplianceResult",
    "InventoryResult",
    "VendorSubmission",
    "VendorValidationResult",
    "KBSearchResult",
    "ToolCallRecord",
    "TraceRecord",
    "AgentState",
    "SessionState",
    # --- Config constants ---
    "VENDOR_POLICY",
    "TOOL_ALLOWLIST",
    "INTENT_TOOLS",
    "KB_VISIBILITY",
    "VALID_INTENTS",
    "VALID_USER_TYPES",
    "US_STATES",
    # --- Data accessors ---
    "get_products",
    "get_inventory",
    "get_customers",
    "get_vendors",
    "get_kb_docs",
    "get_product_by_id",
    "get_product_by_sku",
    "resolve_product",
    "find_alternatives",
    # --- 5 deterministic tools ---
    "hot_picks",
    "compliance_filter",
    "stock_by_warehouse",
    "vendor_validate",
    "kb_search",
    # --- Session state ---
    "get_session",
    "update_session",
    # --- Router ---
    "detect_followup",
    "extract_params",
    "classify_intent",
    "ClassificationError",
    # --- Guardrail nodes ---
    "validate_user",
    "authorize_tools",
    "output_guard",
    # --- Observability ---
    "RequestTracer",
    "estimate_tokens",
    # --- Chain nodes ---
    "sales_chain",
    "compliance_chain",
    "vendor_chain",
    "ops_chain",
    "kb_chain",
]
