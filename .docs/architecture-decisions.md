# Architecture Decisions

## ADR-001: In-memory data layer instead of SQLite

**Decision**: Load seed_data.json into typed Python objects at startup. No SQLite.

**Reason**: The dataset is 60 products, 132 inventory rows, 20 customers, 10 vendors, 3 kb_docs.
In-memory is simpler, faster (<1ms lookups), zero schema management, and the problem statement
explicitly allows it ("You may load this into memory or into a lightweight local store. Keep it simple.").

**Trade-off accepted**: Data does not persist across restarts. This is correct for a PoC.

**Production path**: Replace in-memory dicts with Odoo XML-RPC calls cached in Redis.


## ADR-002: InMemorySaver for LangGraph checkpointing

**Decision**: Use LangGraph's built-in `MemorySaver` (no SQLite checkpointer).

**Reason**: No disk persistence needed in a PoC. `MemorySaver` is simple, zero-dependency,
and avoids the JSON1 SQLite extension risk. The session state we care about (last_intent,
last_state, last_budget, last_product_ids) is tracked separately in `src/state.py`.

**Trade-off accepted**: State lost on process restart. Acceptable for interview demo.


## ADR-003: Tracer registry to avoid LangGraph serialization issues

**Decision**: Store `RequestTracer` in a module-level dict (`src/_registry.py`) keyed by
`request_id`, rather than in LangGraph state.

**Reason**: LangGraph's `MemorySaver` uses msgpack serialization. `RequestTracer` objects
cannot be serialized. Putting them in state would crash the checkpointer.

**Pattern**: `_active_tracers[request_id] = tracer` before graph invocation,
`del _active_tracers[request_id]` in finally block.


## ADR-004: Two-tier intent classification

**Decision**: Keyword scoring (Tier-1, free) + LLM structured output (Tier-2, fallback).

**Reason**: 5 intents over a narrow domain with clear keyword boundaries. Keyword scoring
handles ~95% of queries at zero cost and <1ms. LLM fallback handles novel phrasing.

**LLM failure behavior**: Use best keyword score even if below threshold (with low_confidence flag),
or fail closed with ClassificationError if no keyword signal at all.


## ADR-005: Follow-up is a pre-router step, not a 6th intent

**Decision**: Follow-up queries are detected by `detect_followup()` before classification runs.
The function resolves ordinal references and reuses `last_intent` (always one of the 5 required intents).

**Reason**: The problem statement requires exactly 5 intents. A 6th FOLLOW_UP intent would be
a disqualifier. The pre-router approach correctly routes "add to basket" follow-ups to SALES_RECO
without violating the exact-5-intents constraint.


## ADR-006: output_guard asserts, does not silently filter

**Decision**: If a blocked product survives the chain into the response, mark the request
as DEGRADED and log at ERROR level. Do NOT silently remove the product.

**Reason**: Silent filtering masks bugs in tool logic (e.g., hot_picks returning blocked items).
The degraded flag is observable and triggers investigation. Per plan v5 requirement.


## ADR-007: VENDOR_POLICY as declared config, not inferred from data

**Decision**: `VENDOR_POLICY["lab_report_categories"]` is explicitly declared in `src/models.py`.

**Reason**: The seed data has mixed `lab_report_required` values within THC and Mushroom
categories (reflecting historical products). New vendor submissions follow a blanket policy.
Inferring policy from data would produce incorrect rules.


## ADR-008: Deterministic formatting first, LLM optional

**Decision**: `format_response` always produces deterministic structured text. LLM explanation
is only added when `USE_LLM_FORMATTING=true` AND `OPENAI_API_KEY` is set.

**Reason**: The demo must work without an API key. Deterministic output ensures no API
dependency breaks the live demo. The rubric rewards tool-first truth, not LLM prose.
