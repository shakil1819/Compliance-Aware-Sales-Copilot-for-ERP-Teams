# Fix Plan Review - 2026-04-18

## Scope

Reviewed:

- `C:\Users\Expert\.cursor\plans\fix_3_critical_issues_87bb18db.plan.md`

against:

- current implementation
- [implementation-review-2026-04-18.md](C:/Temp/Interviews/GW/codebase/.docs/implementation-review-2026-04-18.md)
- [implementation-fix-proposal-2026-04-18.md](C:/Temp/Interviews/GW/codebase/.docs/implementation-fix-proposal-2026-04-18.md)

## Verdict

The plan is mostly correct and is directionally good enough to implement, but it has one critical omission and one smaller technical gap.

## What is correct

1. `request_id` unification fix is correct.
   - Passing `request_id` into `RequestTracer` is the right fix.

2. Adding a real redaction helper in `output_guard()` is the right direction.
   - This satisfies the requirement better than a comment-only hook.

3. Adding tests for:
   - full Q1 -> Q5 walkthrough
   - request ID consistency
   - redaction behavior
   is correct and necessary.

## Critical correction needed

### The session fix is incomplete

The plan proposes:

- only overwrite `last_intent` when `intent == SALES_RECO`

That is not sufficient.

### Why it still fails

Current `run_query()` also overwrites `last_product_ids` for:

- `COMPLIANCE_CHECK`
- `OPS_STOCK`

So after:

1. Q1 sales -> `last_product_ids = [sales results]`
2. Q2 compliance -> `last_product_ids = [1003]`
3. Q3 ops -> `last_product_ids = [1008]`

Even if `last_intent` stays `SALES_RECO`, Q5 will resolve `"the first one"` to `1008`, not the top product from Q1.

That means the plan's proposed session fix would still produce the wrong basket item in the required demo order.

### Required correction

The fix must preserve both:

- `last_intent`
- `last_product_ids`

for the last selectable product-list context.

Minimal safe rule:

- only update `last_intent` and `last_product_ids` on `SALES_RECO`
- do not overwrite `last_product_ids` on compliance, ops, vendor, or kb turns

Updating `last_state` and `last_budget` on later turns is still fine.

## Secondary technical gap

### The redaction wiring in the plan is slightly underspecified

The plan says:

- store `redacted_chain_output`
- use it in `_format_with_llm()`

But the current `_format_with_llm()` implementation prompts from `deterministic_text`, not from `chain_output`.

So passing `redacted_chain_output` into `_format_with_llm()` does nothing unless one of these also changes:

1. rebuild the prompt from the redacted payload, or
2. generate a redacted deterministic text first

This is a smaller issue than the session bug, but it should be fixed while implementing.

## Recommended corrected implementation note

In `src/graph.py`, change session update logic so that:

- `SALES_RECO` updates `last_intent` and `last_product_ids`
- all other intents leave those two fields unchanged
- `state` and `budget` may still update if present

And for redaction:

- either prompt the LLM from `redacted_chain_output`
- or build a redacted deterministic text before LLM formatting

## Bottom line

Implement this plan only after correcting the session-state rule for `last_product_ids`. Without that change, the exact live demo sequence from `Problem_Statement.md` will still be wrong.

## Re-check After Plan Update

### Verdict

The updated plan is now implementation-safe.

It fixed the two load-bearing gaps from the prior version:

- it now preserves both `last_intent` and `last_product_ids` by restricting updates to `SALES_RECO`
- it now correctly routes redaction into the actual LLM prompt path by generating redacted deterministic text before `_format_with_llm()`

### What is now correct

1. Session fix
   - Correctly removes the compliance and ops overwrite path for `last_product_ids`
   - Correctly keeps the original sales product list available for Q5

2. Request ID fix
   - Still correct

3. Redaction fix
   - Now acknowledges that `_format_with_llm()` consumes text, not the raw dict
   - Therefore the plan now fixes the real call path rather than only storing redacted state

4. Tests
   - The added tests now match the failure modes that actually matter

### Minor cleanup suggestion

The plan proposes:

- `intent=intent if intent == "SALES_RECO" else None`

That works with the current `update_session()` implementation because falsy values are ignored, but for type clarity it would be cleaner to also update `src/state.py` so the `intent` parameter is typed as `Optional[str]` instead of `str`.

This is not a blocker.

### Final call

The plan is now good to implement.
