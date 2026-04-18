# Plan Review - 2026-04-18

## Scope

Reviewed `C:\Users\Expert\.cursor\plans\ai_chat_service_poc_6124c61a.plan.md` against:

- `Problem_Statement.md`
- current repo state
- actual `data/seed_data (3).json`

## Current repo baseline

- `src/`, `tests/`, `README.md`, and `.docs/` are effectively empty
- `pyproject.toml` has no dependencies
- git repo exists and is clean except for a user change in `.env.example`

## Seed data facts validated

- products: 60
- inventory rows: 132
- customers: 20
- vendors: 10
- kb_docs: 3
- blocked products: 11
- products with `lab_report_required=true`: 7
- category-level `lab_report_required` is not uniform:
  - `THC Beverage`: both `true` and `false` exist
  - `Mushroom Gummies`: both `true` and `false` exist

## Hard challenges

### 1. The plan violates the "exactly one of five intents" rule

Problem statement requires exactly:

- `SALES_RECO`
- `COMPLIANCE_CHECK`
- `VENDOR_ONBOARDING`
- `OPS_STOCK`
- `GENERAL_KB`

The plan adds `FOLLOW_UP` as a sixth routed intent and even gives it its own chain. That is not compliant with the prompt.

Required correction:

- keep follow-up detection as a pre-router resolution step
- reuse `last_intent`
- still output one of the required five intents

### 2. The graph order is logically wrong for authorization

The proposed graph is:

- `input_guard -> classify_intent -> chain`

But the plan also says `input_guard` checks whether the detected intent's tools are allowed for that `user_type`.

That cannot happen before intent classification.

Required correction:

- split into `validate_user_context -> classify_intent -> authorize_intent_tools -> chain`
- or classify first, then perform authorization

### 3. The plan is internally inconsistent on sync vs async SQLite

The todo says:

- "Fully sync stack - no aiosqlite."

But the body later proposes:

- `AsyncSqliteSaver`
- `graph.ainvoke(...)`
- `aiosqlite` in dependencies

This is an avoidable design contradiction. Pick one path and keep it consistent. For this interview, sync is lower risk.

### 4. SQLite is acceptable, but the plan over-invests in it

The prompt explicitly allows:

- reading from JSON directly
- loading into memory
- or a lightweight local store

Given the dataset size, a full SQLite schema, JSON1 dependency check, and dual SQLite usage for data plus checkpointing adds setup risk without helping the rubric much.

Challenge:

- use plain in-memory structures for tools first
- use a minimal in-memory session store for the required memory fields
- add SQLite only if it clearly reduces complexity, which it currently does not

### 5. The plan leaves `review` status undefined

The required tool contract says `compliance_filter` must return:

- allowed
- blocked
- review

The plan defines blocked via `blocked_states`, but does not define deterministic `review` rules.

Required correction:

- explicitly define when `review` happens
- examples: missing state, unresolved product, invalid state code, incomplete compliance metadata

### 6. Vendor validation logic is too coarse for the actual dataset

The plan says lab reports are required for THC and Mushroom categories. The dataset does not support that as a category-wide invariant.

This means the proposed rule is stricter than the seed data and risks contradictory behavior.

Required correction:

- make vendor validation rules explicit in code or config
- do not infer category-wide rules from mixed historical rows
- if category policy is desired, document it as a separate business rule, not as a deduction from the seed data

### 7. The plan relies on unsupported performance and accuracy claims

Examples in the plan:

- keyword tier handles about 80 percent
- tool execution under 10ms
- LLM routing around 300ms
- near-zero token routing for most traffic

None of those claims are backed by measurement in this repo.

Statistical issue:

- five demo prompts are not enough to estimate router accuracy
- even a perfect 5 out of 5 demo pass is only anecdotal, not an accuracy estimate

Required correction:

- replace claims with benchmark tasks
- define a small labeled eval set
- record confusion cases and latency distributions

### 8. The LLM fallback failure mode is wrong

The todo says the LLM classifier should fall back to `GENERAL_KB` on exception.

That is unsafe. An LLM outage would silently misroute compliance or stock queries into a knowledge answer path.

Required correction:

- if LLM fallback fails, use the best deterministic score with low-confidence annotation
- or fail closed with an explicit error

### 9. The plan makes the system less runnable than required

The prompt requires a small runnable PoC. The current plan depends on:

- LLM routing fallback
- LLM response formatting
- LangGraph orchestration
- SQLite checkpointer

Any missing API key or package mismatch can break the demo.

Stronger interview strategy:

- deterministic router first
- deterministic response formatter first
- optional LLM explanation layer behind a feature flag

### 10. `find_alternatives` query is not implementation-ready

The proposed SQL uses:

- `product_id NOT IN (:exclude_ids)`

That does not work as written with a list parameter in standard SQLite bindings.

Required correction:

- generate placeholders dynamically
- or filter excluded ids in Python after query

### 11. Silent output filtering hides bugs

The plan proposes filtering blocked products in `output_guard` if violations are found.

That protects the user, but it can mask earlier logic defects.

Required correction:

- treat output guard as assertion plus audit
- fail the request or mark it degraded if a blocked product survives the chain
- do not silently mutate business-critical compliance output

### 12. Memory proposal exceeds the stated minimum without a clear need

Required state is:

- `last_intent`
- `last_state`
- `last_budget`
- `last_product_ids`

The plan adds `last_results` and full checkpoint persistence. That may be fine, but it is not justified for the PoC.

Required correction:

- keep only the required fields first
- resolve follow-ups from `last_product_ids`
- re-query deterministic tool data when needed

## Recommended simpler plan

### Phase 1

- parse JSON once at startup into typed Python objects
- implement deterministic tool functions over in-memory collections
- implement rule-based router with exact one-of-five intents
- add a tiny session store keyed by session id
- add structured JSON logs

### Phase 2

- add compliance alternatives helper
- add allowlist enforcement after routing
- add deterministic response formatting
- add tests for tools, router, and five live demo prompts

### Phase 3

- optionally add LangGraph if time remains
- optionally add LLM explanation formatting behind a flag

## Bottom line

The plan has good instincts around separation of concerns, observability, and deterministic tools. But in its current form it is too large, internally inconsistent, and not fully compliant with the prompt. The highest-risk failures are the sixth intent, the broken auth ordering, the undefined `review` semantics, and the unnecessary operational complexity for a time-boxed PoC.

## Re-evaluation Against Problem_Statement.md After Plan v4

### What improved

- sync versus async inconsistency was reduced by switching to sync `SqliteSaver`
- token estimation and timeout behavior are now explicitly documented
- `detect_followup`, `extract_params`, and `classify_intent` are separated more cleanly
- `VendorSubmission` is now explicitly typed

### What is still wrong

1. The plan still violates the exact-five-intents requirement.
   - The problem statement requires routing into exactly one of five intents.
   - The plan still routes to `FOLLOW_UP` in the graph and demo section.

2. The authorization story is still muddled.
   - The graph still starts with `input_guard -> classify_intent`.
   - The text then says classification performs allowlist checks.
   - This is better than before, but the design is still split across two places and is not cleanly modeled.

3. The LLM failure default is still unsafe.
   - Defaulting to `GENERAL_KB` on classifier exception can silently misroute a compliance or stock query.
   - A safe fallback should preserve the best deterministic label or fail closed.

4. The plan is still too large for the prompt.
   - The prompt allows direct JSON or lightweight local storage and minimal memory.
   - The plan still includes SQLite schema work, checkpoint persistence, LangGraph, cache layer, query-log table, and LLM formatting.
   - That is still more system than the problem asks for.

5. The compliance `review` path is still not properly defined.
   - `allowed/blocked/review` is required.
   - The plan still mostly explains `blocked`, but does not define crisp deterministic conditions for `review`.

6. The vendor validation rule is still over-assumed.
   - The plan still says lab reports are required for THC and Mushroom categories.
   - The actual seed data does not support that as a strict category-wide fact.
   - If that rule is desired, it must be declared as policy, not inferred from the dataset.

7. The caching and query-log additions are not justified for the interview deliverable.
   - They are not catastrophic, but they are not load-bearing for the rubric either.
   - In a time-boxed build, they increase surface area before the core demo is proven.

### Updated conclusion

Plan v4 is better than the earlier draft, but the answer to "is it over-engineered relative to the problem statement" is still yes. It improved internal consistency, not scope discipline.
