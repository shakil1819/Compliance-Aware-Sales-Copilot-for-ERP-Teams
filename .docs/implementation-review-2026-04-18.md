# Implementation Review - 2026-04-18

## Scope

Reviewed the current implementation against:

- `Problem_Statement.md`
- scoring rubric in `Problem_Statement.md`
- current code in `src/`, `tests/`, `main.py`, `README.md`

## Verification performed

- Read all core source files and tests
- Ran full test suite: `uv run pytest`
- Manually exercised the live demo flow and a focused observability check

## Findings

### 1. Required live demo follow-up flow does not work in the documented Q1 -> Q5 order

The problem statement's live demo sequence ends with:

- Q1 sales
- Q2 compliance
- Q3 ops
- Q4 vendor onboarding
- Q5 follow-up: "Ok add 2 of the first one to the basket"

Current implementation only supports the follow-up when it immediately follows the sales recommendation turn. `run_query()` overwrites `last_intent` and `last_product_ids` on later turns, so after Q4 the basket follow-up reuses `VENDOR_ONBOARDING` instead of the original sales context.

Affected areas:

- `src/graph.py` session update logic
- `src/state.py` minimal overwrite behavior
- `tests/test_demo.py` only tests follow-up immediately after Q1, not after the full live-demo sequence

Observed manual result:

- after Q1 -> Q4, Q5 resolves to `VENDOR_ONBOARDING` and returns a vendor validation failure instead of a basket simulation

### 2. Observability request IDs are inconsistent between API result and trace logs

`run_query()` creates one `request_id` and returns it to the caller, but `RequestTracer` creates a different UUID internally and writes that different value to `.logs/traces.jsonl`.

This breaks traceability:

- caller-visible `request_id` cannot be matched to the persisted trace
- tool-call audit and request-level debugging become unreliable

Affected areas:

- `src/graph.py`
- `src/observability.py`

Observed manual result:

- returned `request_id` differed from the last trace line `request_id` for the same request

### 3. The code claims a PII redaction hook exists, but no redaction is implemented

The problem statement explicitly asks to show where and how PII would be redacted before sending data to an LLM.

`output_guard()` documents a PII redaction hook, but the implementation only checks for blocked product leaks. There is no actual redaction step or even a stub that transforms data before `_format_with_llm()`.

Affected area:

- `src/guardrails.py`

## Rubric view

### Architecture clarity

- Strong
- Modules are separated cleanly: data, router, tools, guardrails, state, observability, graph

### Tool-first correctness

- Mostly strong
- Deterministic tools are implemented and canonical chains exist
- Main gap is the live-demo memory path, which currently fails in the required sequence

### Token and latency efficiency

- Strong
- In-memory data, keyword-first routing, and deterministic formatting keep the system cheap

### Compliance gating

- Strong
- `blocked/allowed/review` is deterministic
- sales output excludes blocked products

### Observability

- Partial
- trace structure exists and logs are emitted
- request ID mismatch is a material defect against auditability

### Code quality

- Strong
- tests pass
- README is clear
- code is readable
- but one important scenario is incorrectly tested

## Bottom line

The implementation is close to the target and passes its current test suite, but it is not fully compliant with the problem statement yet. The biggest issue is that the required live demo follow-up scenario fails in the stated demo order. The second major issue is the observability `request_id` mismatch, which weakens auditability.
