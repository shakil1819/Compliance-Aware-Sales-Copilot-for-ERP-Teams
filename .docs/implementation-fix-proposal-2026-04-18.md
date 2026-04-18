# Implementation Fix Proposal - 2026-04-18

## Scope

This proposal fixes the three review findings from [implementation-review-2026-04-18.md](C:/Temp/Interviews/GW/codebase/.docs/implementation-review-2026-04-18.md):

1. Q5 follow-up fails after the full live-demo sequence
2. `request_id` differs between API response and trace log
3. PII redaction is documented but not implemented

## Goals

- Pass the exact live-demo order from `Problem_Statement.md`
- Make observability request tracing one-to-one and auditable
- Add a real pre-LLM redaction step
- Keep LangChain and LangGraph in place
- Avoid widening session state beyond the required four fields

## Fix 1 - Follow-up resolution must survive Q1 -> Q4 -> Q5

### Root cause

`run_query()` overwrites:

- `last_intent`
- `last_product_ids`

on every qualifying turn. After Q4, session state points at vendor onboarding, so Q5 no longer resolves against the original sales list.

### Design decision

Do not expand session state. Keep the required four fields only.

Instead, preserve the most recent product-list context only when the turn actually produces a list of user-selectable products. That means:

- `SALES_RECO`: update `last_product_ids`
- `COMPLIANCE_CHECK`: do not overwrite `last_product_ids`
- `OPS_STOCK`: do not overwrite `last_product_ids`
- `VENDOR_ONBOARDING`: do not overwrite `last_product_ids`
- `GENERAL_KB`: do not overwrite `last_product_ids`

Also preserve `last_intent` for follow-up selection semantics by only updating it when the turn produces a follow-up-selectable product context or when no prior product context exists.

### Minimal code change

In `src/graph.py`:

1. Replace unconditional session updates with conditional updates.
2. Treat only `SALES_RECO` as the source of `"the first one"` product list context.
3. For basket follow-ups, do not require the current last turn to be sales. Reuse the stored sales list if it exists.

### Proposed behavior

- Q1 sales stores the ranked product ids
- Q2 and Q3 may update `last_state` and `last_budget`, but do not destroy the sales list
- Q4 vendor validation does not destroy the sales list
- Q5 resolves `"the first one"` back to the Q1 ranked list and performs basket simulation

### File changes

- `src/graph.py`
- `tests/test_demo.py`

### Test additions

Add one explicit end-to-end test for the exact walkthrough order:

1. sales
2. compliance
3. ops
4. vendor onboarding
5. follow-up basket

Assertions:

- final intent is `SALES_RECO`
- response contains basket simulation text
- response references `SKU-1016` or the top product from Q1

## Fix 2 - Unify request IDs across response and trace log

### Root cause

`run_query()` creates a `request_id`, but `RequestTracer` creates a second UUID internally.

### Design decision

`run_query()` is the source of truth for request identity.

Pass that value into `RequestTracer` so the returned payload, in-memory registry, and persisted trace all share the same ID.

### Minimal code change

In `src/observability.py`:

- change `RequestTracer.__init__` to accept an optional `request_id: str | None = None`
- if provided, use it
- otherwise generate one

In `src/graph.py`:

- instantiate `RequestTracer(session_id=session_id, user_type=user_type, request_id=request_id)`

### File changes

- `src/observability.py`
- `src/graph.py`

### Test additions

Add one focused test:

- run a query
- capture returned `request_id`
- read the last JSONL trace line
- assert the IDs match

Suggested file:

- `tests/test_demo.py` or `tests/test_observability.py`

## Fix 3 - Implement real PII redaction before optional LLM formatting

### Root cause

`output_guard()` claims a redaction hook exists, but no redaction is performed before `_format_with_llm()`.

### Design decision

Implement a lightweight deterministic redaction pass now.

The current tool outputs do not heavily expose customer PII, but the problem statement explicitly asks to show where and how redaction happens. The implementation should therefore be real, not only commented.

### Redaction approach

Create a helper that redacts obvious sensitive fields from any dict/list payload before LLM formatting:

- `name` only when attached to customer/vendor entities, not product names
- `customer_id`
- `vendor_id`
- any future fields matching:
  - `email`
  - `phone`
  - `address`

Because current chain outputs are product-focused, the initial redaction can be narrow and explicit:

- redact `submission.name` in vendor onboarding output before LLM formatting
- redact any future `customer_*` or `vendor_*` identifiers if present

### Minimal code change

In `src/guardrails.py`:

- add `redact_for_llm(chain_output: dict) -> dict`
- return sanitized `chain_output` in state as `redacted_chain_output`

In `src/graph.py`:

- prefer `redacted_chain_output` over `chain_output` inside `_format_with_llm()`

### File changes

- `src/guardrails.py`
- `src/graph.py`

### Test additions

Add one focused test with `USE_LLM_FORMATTING=true` mocked or with the formatter helper called directly:

- provide a `vendor_submission.name`
- run through `output_guard`
- assert the redacted payload does not expose raw vendor name to the LLM input builder

## Implementation order

1. Fix request ID unification
2. Fix session update semantics for the Q1 -> Q5 walkthrough
3. Add the missing live-demo-sequence test
4. Add deterministic redaction helper and test
5. Re-run full test suite
6. Re-run manual walkthrough in the exact problem-statement order

## Acceptance criteria

- `uv run pytest` passes
- exact walkthrough order succeeds:
  - Q1 sales
  - Q2 compliance
  - Q3 ops
  - Q4 vendor onboarding
  - Q5 basket follow-up
- returned `request_id` equals logged trace `request_id`
- a real redaction function exists and is invoked before optional LLM formatting

## Trade-offs

- Preserving sales product context across later turns slightly biases follow-up handling toward the last selectable product list, which is what the live demo expects
- We intentionally do not add more session fields because the prompt explicitly asks for minimal memory
- Redaction remains deterministic and lightweight to avoid turning this into a generalized data-loss-prevention subsystem
