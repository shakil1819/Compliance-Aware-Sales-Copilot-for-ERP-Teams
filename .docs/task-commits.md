# Task-Commit Mapping

## 2026-04-18 - Implementation Sprint

| Task | File(s) | Notes |
|---|---|---|
| Project scaffold | pyproject.toml, .env.example | UV-managed deps: langgraph, langchain-openai, pydantic, python-dotenv |
| Models | src/models.py | Pydantic schemas, VENDOR_POLICY, TOOL_ALLOWLIST, INTENT_TOOLS, KB_VISIBILITY |
| Data layer | src/data.py | In-memory load from seed_data.json. resolve_product(), find_alternatives() |
| 5 deterministic tools | src/tools.py | hot_picks, compliance_filter (3-way), stock_by_warehouse, vendor_validate, kb_search |
| Router | src/router.py | detect_followup(), extract_params() (US_STATES set), classify_intent() (2-tier) |
| State | src/state.py | In-memory session dict with exactly 4 fields |
| Guardrails | src/guardrails.py | validate_user, authorize_tools, output_guard (assert, not filter) |
| Observability | src/observability.py | RequestTracer context manager, JSONL traces to .logs/ |
| Tracer registry | src/_registry.py | Avoids LangGraph serialization issue with non-serializable tracer |
| Chains | src/chains.py | 5 chain nodes + basket follow-up simulation |
| Graph | src/graph.py | LangGraph StateGraph, format_response, run_query() |
| CLI | main.py | VENDOR_JSON: prefix for vendor submissions |
| Unit tests | tests/test_tools.py, tests/test_router.py | 48 tests, all pass |
| E2E tests | tests/test_demo.py | 29 tests covering all 5 demo scenarios + permissions |
| README | README.md | One-command start, architecture, module map, demo script |
| Architecture docs | .docs/architecture-decisions.md | 8 ADRs |

## Key Fix Log

| Bug | Fix |
|---|---|
| State regex matching "ME" from "give me" | Removed lowercase fallback; only uppercase US_STATES matching |
| Budget regex matching SKU number digits | Strip SKU-XXXX before budget extraction; require "under" prefix |
| Quantity regex too greedy (matched any number) | Require explicit context: "add N", "N units", "qty N" |
| RequestTracer not msgpack-serializable | Move tracer to _registry.py module-level dict, not in LangGraph state |
| vendor_submission cleared in classify node | Preserve existing value from state instead of overwriting with {} |
| Follow-up basket showing full product list | Detect basket_action flag in params; short-circuit to basket simulation output |

## 2026-04-18 - Proposed Next Fixes

| Proposed task | Planned file(s) | Reason |
|---|---|---|
| Preserve sales selection context across Q1 -> Q5 walkthrough | src/graph.py, tests/test_demo.py | Current session overwrite breaks required follow-up demo order |
| Unify request IDs between API response and trace log | src/graph.py, src/observability.py, tests | Current traceability is broken |
| Add real PII redaction before optional LLM formatting | src/guardrails.py, src/graph.py, tests | Requirement is documented but not implemented |
