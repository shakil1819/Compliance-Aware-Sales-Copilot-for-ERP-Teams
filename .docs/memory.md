# Working Memory

## 2026-04-18

- User asked to evaluate and challenge `C:\Users\Expert\.cursor\plans\ai_chat_service_poc_6124c61a.plan.md`.
- Current repo implementation is mostly empty.
- Existing unrelated user change is present in `.env.example`. Do not modify or revert it.
- The seed dataset is small enough that in-memory deterministic tooling is the lowest-risk baseline.
- Any future implementation must preserve:
  - exactly five intents
  - deterministic tool-first truth
  - user_type allowlists
  - minimal session state
  - structured observability
- Re-evaluation of the newer plan version: improved consistency, but still over-engineered and still non-compliant because `FOLLOW_UP` remains a sixth routed intent.
- Latest plan re-check: v5 fixed the biggest architecture mistakes. Current stance is "slightly overbuilt but defensible", with remaining issues in consistency and follow-up basket semantics.
- User clarified: LangChain and LangGraph are mandatory, not optional. Future plan reviews must treat them as baseline requirements for this backend.
- Implementation review status:
  - tests pass
  - required live-demo Q5 follow-up still fails after the full Q1 -> Q4 sequence
  - observability request IDs are inconsistent between response and trace log
  - PII redaction is documented but not implemented
- Fix proposal added:
  - keep sales product-list context across later non-list turns
  - unify request IDs by passing request_id into RequestTracer
  - implement deterministic redaction helper before optional LLM formatting
- Review of external fix plan:
  - good overall
  - must also preserve `last_product_ids`, not only `last_intent`
  - redaction must affect the actual LLM prompt path, not only stored state
- Updated fix plan re-check:
  - now safe to implement
  - only minor cleanup suggestion remains around `update_session()` intent typing
- Logging/settings update completed:
  - `src/settings.py` added with `configs`
  - `src/logging_config.py` added with Loguru bootstrap
  - runtime code now reads config through `configs.<key>`
  - application logs write to `.logs/application.log`
  - tests still pass
