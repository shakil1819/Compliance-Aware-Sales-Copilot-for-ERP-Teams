"""
Streamlit demo UI for the AI Chat Service PoC.

Run with:  uv run streamlit run app.py
"""

from __future__ import annotations

import uuid

import streamlit as st

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="GreenWave AI Chat",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Load graph once (cached across reruns)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="Loading product data and building graph…")
def _get_graph():
    from src.graph import build_graph
    return build_graph()


graph = _get_graph()

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []          # list[dict] – chat history
if "pending_query" not in st.session_state:
    st.session_state.pending_query = None   # pre-filled from demo button
if "pending_vendor" not in st.session_state:
    st.session_state.pending_vendor = None

# ---------------------------------------------------------------------------
# Demo queries (the exact live-demo sequence from Problem_Statement.md)
# ---------------------------------------------------------------------------

DEMO_QUERIES = [
    {
        "label": "Q1 · Hot Picks",
        "icon": "🔥",
        "tag": "SALES_RECO",
        "query": "Give me hot picks for CA under 5000",
        "user_type": "internal_sales",
        "vendor_submission": None,
        "tip": "Shows top-ranked CA-compliant products under $5,000.",
    },
    {
        "label": "Q2 · Compliance",
        "icon": "⚖️",
        "tag": "COMPLIANCE_CHECK",
        "query": "Why is SKU-1003 not available in CA? Suggest alternatives",
        "user_type": "internal_sales",
        "vendor_submission": None,
        "tip": "Explains REVIEW status for THC Beverage and offers alternatives.",
    },
    {
        "label": "Q3 · Stock Check",
        "icon": "📦",
        "tag": "OPS_STOCK",
        "query": "How much stock does SKU-1008 have and where?",
        "user_type": "internal_sales",
        "vendor_submission": None,
        "tip": "Returns warehouse-by-warehouse inventory for SKU-1008.",
    },
    {
        "label": "Q4 · Vendor Upload",
        "icon": "📋",
        "tag": "VENDOR_ONBOARDING",
        "query": "I am uploading a product missing Net Wt and no lab report - what do I fix?",
        "user_type": "portal_vendor",
        "vendor_submission": {"category": "THC Beverage", "lab_report_attached": False},
        "tip": "Vendor policy check – returns FAIL with exact missing fields.",
    },
    {
        "label": "Q5 · Add to Basket",
        "icon": "🛒",
        "tag": "SALES_RECO (follow-up)",
        "query": "Ok add 2 of the first one to the basket",
        "user_type": "internal_sales",
        "vendor_submission": None,
        "tip": "Follow-up: resolves 'first one' from Q1 session and simulates basket add.",
    },
]

INTENT_COLORS = {
    "SALES_RECO": "#1a8a44",
    "COMPLIANCE_CHECK": "#c0392b",
    "VENDOR_ONBOARDING": "#2471a3",
    "OPS_STOCK": "#7d3c98",
    "GENERAL_KB": "#d35400",
}

USER_TYPE_ICONS = {
    "internal_sales": "👤 Internal Sales",
    "portal_vendor": "🏭 Portal Vendor",
    "portal_customer": "🛍️ Portal Customer",
}

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.image("https://placehold.co/200x60/1a8a44/white?text=GreenWave+AI", width=200)
    st.markdown("### AI Chat Service PoC")
    st.markdown("Production-grade agentic assistant over mock ERP data.")

    st.divider()

    st.markdown("#### 🎯 Demo Sequence")
    st.caption("Click any query to send it. Run Q1→Q5 in order for the full live demo.")

    for i, dq in enumerate(DEMO_QUERIES):
        col_icon, col_btn = st.columns([0.12, 0.88])
        with col_icon:
            st.markdown(f"<div style='font-size:22px;margin-top:6px'>{dq['icon']}</div>",
                        unsafe_allow_html=True)
        with col_btn:
            if st.button(
                dq["label"],
                key=f"demo_btn_{i}",
                help=dq["tip"],
                use_container_width=True,
            ):
                st.session_state.pending_query = dq["query"]
                st.session_state.pending_user_type = dq["user_type"]
                st.session_state.pending_vendor = dq["vendor_submission"]

    st.divider()

    if st.button("▶ Run Full Demo (Q1 → Q5)", use_container_width=True, type="primary"):
        st.session_state.run_full_demo = True

    st.divider()

    st.markdown("#### ⚙️ Settings")
    user_type = st.selectbox(
        "User type",
        ["internal_sales", "portal_vendor", "portal_customer"],
        format_func=lambda x: USER_TYPE_ICONS[x],
    )

    if st.button("🔄 New Session", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.pending_query = None
        st.session_state.pending_vendor = None
        st.rerun()

    st.divider()
    st.markdown("#### ℹ️ When is LLM called?")
    st.markdown(
        """
**Tier-2 classification** — only when keyword score < 0.05  
**LLM formatting** — only when `USE_LLM_FORMATTING=true`

Without `OPENAI_API_KEY` the system runs **100% deterministically** on keywords + rule-based tools.
        """
    )

    from src.settings import configs as _cfg
    from src.langsmith_config import langsmith_active as _ls_active

    if _cfg.openai_api_key:
        st.success("🔑 OPENAI_API_KEY loaded")
    else:
        st.info("🔑 No API key — keyword-only mode")

    if _cfg.use_llm_formatting:
        st.success("✨ LLM formatting ON")
    else:
        st.caption("✨ LLM formatting OFF")

    st.divider()
    st.markdown("#### 🔭 LangSmith Tracing")
    if _ls_active:
        project_url = (
            f"https://smith.langchain.com/projects/p/"
            f"{_cfg.langsmith_project}"
        )
        st.success(f"🟢 Tracing **ON** — [{_cfg.langsmith_project}]({project_url})")
        st.caption("Every request → LangSmith. All nodes, tools, and LLM calls captured.")
    else:
        st.info("⚪ Tracing OFF — set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY`")

    st.caption(f"Session: `{st.session_state.session_id[:8]}…`")

# ---------------------------------------------------------------------------
# Main panel header
# ---------------------------------------------------------------------------

st.markdown(
    """
    <h1 style='margin-bottom:0'>🌿 GreenWave AI Chat</h1>
    <p style='color:#666;margin-top:4px'>
    Agentic ERP assistant — 5 intents · deterministic tools · session-aware follow-ups
    </p>
    """,
    unsafe_allow_html=True,
)
st.divider()

# ---------------------------------------------------------------------------
# Helper: render one chat turn
# ---------------------------------------------------------------------------

def _intent_badge(intent: str) -> str:
    color = INTENT_COLORS.get(intent, "#555")
    return (
        f"<span style='background:{color};color:white;border-radius:4px;"
        f"padding:2px 8px;font-size:12px;font-weight:600'>{intent}</span>"
    )


def _tier_badge(tier: str | None) -> str:
    color = "#1a8a44" if tier == "keyword" else "#2471a3"
    label = "⚡ keyword" if tier == "keyword" else "🤖 LLM"
    return (
        f"<span style='background:{color};color:white;border-radius:4px;"
        f"padding:2px 6px;font-size:11px'>{label}</span>"
    )


def _render_assistant_turn(result: dict) -> None:
    """Render one assistant response card."""
    intent = result.get("intent", "")
    tier = result.get("classification_tier")
    tools = result.get("tool_results", [])
    latency = result.get("latency_ms", 0)
    degraded = result.get("degraded", False)
    text = result.get("response_text", "")

    # Meta row
    meta_html = (
        f"{_intent_badge(intent)}&nbsp;&nbsp;"
        f"{_tier_badge(tier)}&nbsp;&nbsp;"
    )
    if degraded:
        meta_html += "<span style='color:#c0392b;font-size:12px'>⚠️ DEGRADED</span>&nbsp;&nbsp;"
    if latency:
        meta_html += f"<span style='color:#888;font-size:11px'>⏱ {latency:.1f} ms</span>"

    st.markdown(meta_html, unsafe_allow_html=True)

    # Response text
    st.markdown(text)

    # Tools expander
    if tools:
        with st.expander(f"🔧 Tools called ({len(tools)})", expanded=False):
            for t in tools:
                name = t.get("name", "")
                args = t.get("args", {})
                lat = t.get("latency_ms", 0)
                res = t.get("result_summary", "")
                st.markdown(
                    f"**`{name}`** &nbsp; `{lat:.1f} ms`",
                    unsafe_allow_html=True,
                )
                if args:
                    st.json(args, expanded=False)
                if res:
                    st.caption(f"↳ {res[:200]}")


# ---------------------------------------------------------------------------
# Helper: run one query and record in history
# ---------------------------------------------------------------------------

def _run_turn(query: str, ut: str, vendor_submission=None) -> dict:
    from src.graph import run_query
    import time

    t0 = time.monotonic()
    result = run_query(
        graph,
        query,
        ut,
        st.session_state.session_id,
        vendor_submission=vendor_submission,
    )
    elapsed_ms = (time.monotonic() - t0) * 1000
    result["latency_ms"] = elapsed_ms

    st.session_state.messages.append({
        "role": "user",
        "content": query,
        "user_type": ut,
    })
    st.session_state.messages.append({
        "role": "assistant",
        "result": result,
    })
    return result


# ---------------------------------------------------------------------------
# Full demo run (triggered from sidebar button)
# ---------------------------------------------------------------------------

if st.session_state.get("run_full_demo"):
    st.session_state.run_full_demo = False
    # Reset session for a clean demo
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []

    progress = st.progress(0, text="Running full demo sequence…")
    for i, dq in enumerate(DEMO_QUERIES):
        progress.progress((i) / len(DEMO_QUERIES), text=f"Running {dq['label']}…")
        _run_turn(dq["query"], dq["user_type"], dq.get("vendor_submission"))
    progress.progress(1.0, text="Demo complete!")
    st.rerun()

# ---------------------------------------------------------------------------
# Render chat history
# ---------------------------------------------------------------------------

chat_container = st.container()

with chat_container:
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            with st.chat_message("user"):
                ut_label = USER_TYPE_ICONS.get(msg["user_type"], msg["user_type"])
                st.caption(ut_label)
                st.markdown(msg["content"])
        else:
            with st.chat_message("assistant", avatar="🌿"):
                _render_assistant_turn(msg["result"])

# ---------------------------------------------------------------------------
# Handle pending query from demo button (runs after history render)
# ---------------------------------------------------------------------------

if st.session_state.pending_query:
    pq = st.session_state.pending_query
    put = st.session_state.get("pending_user_type", user_type)
    pv = st.session_state.pending_vendor
    st.session_state.pending_query = None
    st.session_state.pending_vendor = None

    with st.chat_message("user"):
        st.caption(USER_TYPE_ICONS.get(put, put))
        st.markdown(pq)

    with st.chat_message("assistant", avatar="🌿"):
        with st.spinner("Thinking…"):
            result = _run_turn(pq, put, pv)
        _render_assistant_turn(result)

    st.rerun()

# ---------------------------------------------------------------------------
# Chat input at the bottom
# ---------------------------------------------------------------------------

st.divider()

# Quick-launch chips above the chat input
st.markdown("**Quick launch:**")
chip_cols = st.columns(len(DEMO_QUERIES))
for i, dq in enumerate(DEMO_QUERIES):
    with chip_cols[i]:
        if st.button(
            f"{dq['icon']} {dq['tag'].split(' ')[0]}",
            key=f"chip_{i}",
            help=dq["tip"],
            use_container_width=True,
        ):
            st.session_state.pending_query = dq["query"]
            st.session_state.pending_user_type = dq["user_type"]
            st.session_state.pending_vendor = dq["vendor_submission"]
            st.rerun()

# ---------------------------------------------------------------------------
# Vendor submission panel (optional structured input for VENDOR_ONBOARDING)
# ---------------------------------------------------------------------------

with st.expander("📋 Vendor submission JSON (optional — for vendor validation queries)", expanded=False):
    st.caption(
        "Paste a JSON object with your product fields. "
        "This is passed directly to `vendor_validate` alongside your query text. "
        "You can also prefix your message with `VENDOR_JSON:{...}` in the chat box below."
    )

    _vs_template = """{
  "name": "My Product",
  "category": "THC Beverage",
  "net_wt_oz": 3.5,
  "net_vol_ml": 100.0,
  "nicotine_mg": null,
  "lab_report_attached": false
}"""
    vendor_json_text = st.text_area(
        "Vendor submission JSON",
        value="",
        height=160,
        placeholder=_vs_template,
        label_visibility="collapsed",
    )

    _parsed_vendor: dict | None = None
    if vendor_json_text.strip():
        try:
            _parsed_vendor = __import__("json").loads(vendor_json_text)
            st.success("✅ Valid JSON — will be attached to your next query")
        except Exception as _je:
            st.error(f"Invalid JSON: {_je}")

    if _parsed_vendor:
        st.session_state["_manual_vendor"] = _parsed_vendor
    else:
        st.session_state.pop("_manual_vendor", None)


# ---------------------------------------------------------------------------
# Parse VENDOR_JSON: prefix from raw chat input (same as CLI behaviour)
# ---------------------------------------------------------------------------

def _parse_chat_input(raw: str) -> tuple[str, dict | None]:
    """
    Extract optional VENDOR_JSON:{...} prefix from the chat input string.
    Returns (cleaned_query, vendor_submission_dict_or_None).
    Matches the CLI prefix behaviour in main.py.
    """
    import json as _json
    if raw.upper().startswith("VENDOR_JSON:"):
        rest = raw[len("VENDOR_JSON:"):]
        try:
            brace_end = rest.index("}") + 1
            vendor = _json.loads(rest[:brace_end])
            query = rest[brace_end:].strip() or "Validate this vendor submission"
            return query, vendor
        except (ValueError, _json.JSONDecodeError):
            pass  # fall through — treat the whole string as a plain query
    return raw, None


chat_input = st.chat_input(
    "Ask anything… or prefix with VENDOR_JSON:{…} for vendor validation"
)

if chat_input:
    query_text, inline_vendor = _parse_chat_input(chat_input)
    # inline prefix takes priority; then the expander panel; then None
    vendor_payload = inline_vendor or st.session_state.pop("_manual_vendor", None)

    # Show user bubble with the cleaned query text (not the raw JSON prefix)
    with st.chat_message("user"):
        st.caption(USER_TYPE_ICONS.get(user_type, user_type))
        st.markdown(query_text)
        if vendor_payload:
            st.caption(f"📋 vendor_submission: `{vendor_payload}`")

    with st.chat_message("assistant", avatar="🌿"):
        with st.spinner("Thinking…"):
            result = _run_turn(query_text, user_type, vendor_submission=vendor_payload)
        _render_assistant_turn(result)

    st.rerun()
