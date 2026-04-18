# AI Chat Service PoC

Tool-first agentic backend over mock ERP data with deterministic compliance, LangGraph orchestration, minimal session state, and structured observability.

## How To Run

One command:

```bash
uv run main.py
```

Notes:
- `uv run` uses the project environment and lockfile.
- Copy `.env.example` to `.env` only if you want optional OpenAI-backed classification fallback or optional LLM response polishing.
- No database setup. No Docker. Data loads from `data/seed_data (3).json` at startup.

## Architecture Overview

```mermaid
flowchart TD
    classDef startEnd fill:#E8F5E9,stroke:#2E7D32,color:#1B4332,stroke-width:2px
    classDef process fill:#EAF4FF,stroke:#4F83CC,color:#16324F,stroke-width:1.5px
    classDef decision fill:#FFF7E8,stroke:#D4A24C,color:#5B4636,stroke-width:1.5px
    classDef tool fill:#E8F7F2,stroke:#4CA68B,color:#134E4A,stroke-width:1.5px
    classDef trace fill:#F4F6F8,stroke:#78909C,color:#263238,stroke-width:1.5px
    classDef llm fill:#F9F3E8,stroke:#C28B4E,color:#5A3E1B,stroke-width:1.5px

    subgraph INGRESS["`Ingress`"]
        direction LR
        I0["`START`"]:::startEnd --> I1["`user query`"]:::process
        I1 --> I2["`validate_user`"]:::decision
        I2 -- "`valid`" --> I3["`validated request`"]:::process
        I2 -- "`invalid user_type`" --> I5["`END`"]:::startEnd
        I3 --> I4["`END`"]:::startEnd
    end

    subgraph ROUTING["`Routing`"]
        direction LR
        R0["`START`"]:::startEnd --> R1["`detect_followup`"]:::decision
        R1 --> R2["`extract_params`"]:::process
        R2 --> R3["`keyword router`"]:::decision
        R3 -- "`keyword match`" --> R5["`intent selected`"]:::process
        R3 -- "`ambiguous`" --> R4["`OpenAI fallback`"]:::llm
        R4 --> R5
        R5 --> R6["`END`"]:::startEnd
    end

    subgraph AUTH["`Authorization`"]
        direction LR
        A0["`START`"]:::startEnd --> A1["`authorize_tools`"]:::decision
        A1 -- "`allowed`" --> A2["`allowed intent path`"]:::process
        A1 -- "`denied`" --> A4["`denied response`"]:::trace
        A2 --> A3["`END`"]:::startEnd
        A4 --> A5["`END`"]:::startEnd
    end

    subgraph SALES["`SALES_RECO`"]
        direction LR
        S0["`START`"]:::startEnd --> S1["`hot_picks`"]:::tool
        S1 --> S2["`compliance_filter`"]:::tool
        S2 --> S3["`END`"]:::startEnd
    end

    subgraph COMPLIANCE["`COMPLIANCE_CHECK`"]
        direction LR
        C0["`START`"]:::startEnd --> C1["`resolve_product`"]:::tool
        C1 --> C2["`compliance_filter`"]:::tool
        C2 --> C3["`find_alternatives`"]:::tool
        C3 --> C4["`END`"]:::startEnd
    end

    subgraph VENDOR["`VENDOR_ONBOARDING`"]
        direction LR
        V0["`START`"]:::startEnd --> V1["`vendor_validate`"]:::tool
        V1 --> V2["`END`"]:::startEnd
    end

    subgraph OPS["`OPS_STOCK`"]
        direction LR
        O0["`START`"]:::startEnd --> O1["`resolve_product`"]:::tool
        O1 --> O2["`stock_by_warehouse`"]:::tool
        O2 --> O3["`END`"]:::startEnd
    end

    subgraph KB["`GENERAL_KB`"]
        direction LR
        K0["`START`"]:::startEnd --> K1["`kb_search`"]:::tool
        K1 --> K2["`END`"]:::startEnd
    end

    subgraph RESPONSE["`Response And Trace`"]
        direction LR
        P0["`START`"]:::startEnd --> P1["`output_guard`"]:::decision
        P1 --> P2["`deterministic formatter`"]:::process
        P2 --> P3["`optional LLM polish`"]:::llm
        P3 --> P4["`RequestTracer`"]:::trace
        P4 --> P5["`END`"]:::startEnd
    end

    I4 --> R0
    R6 --> A0
    A3 -- "`SALES_RECO`" --> S0
    A3 -- "`COMPLIANCE_CHECK`" --> C0
    A3 -- "`VENDOR_ONBOARDING`" --> V0
    A3 -- "`OPS_STOCK`" --> O0
    A3 -- "`GENERAL_KB`" --> K0
    S3 --> P0
    C4 --> P0
    V2 --> P0
    O3 --> P0
    K2 --> P0

    style INGRESS fill:#F7FBFF,stroke:#B7C7D6,stroke-width:1px,color:#1F2937
    style ROUTING fill:#F9FCFF,stroke:#B7C7D6,stroke-width:1px,color:#1F2937
    style AUTH fill:#FFFCF5,stroke:#D8C59A,stroke-width:1px,color:#1F2937
    style SALES fill:#F4FBF7,stroke:#AFCFBF,stroke-width:1px,color:#1F2937
    style COMPLIANCE fill:#F4FBF7,stroke:#AFCFBF,stroke-width:1px,color:#1F2937
    style VENDOR fill:#F4FBF7,stroke:#AFCFBF,stroke-width:1px,color:#1F2937
    style OPS fill:#F4FBF7,stroke:#AFCFBF,stroke-width:1px,color:#1F2937
    style KB fill:#F4FBF7,stroke:#AFCFBF,stroke-width:1px,color:#1F2937
    style RESPONSE fill:#F8FAFB,stroke:#B7C7D6,stroke-width:1px,color:#1F2937
```

Flow notes:
- `validate_user` runs first. Invalid `user_type` requests stop before routing or tool calls.
- `classify_intent` keeps routing cheap with keyword logic first and only uses OpenAI fallback when the query is ambiguous and `OPENAI_API_KEY` is configured.
- `authorize_tools` enforces per-user-type allowlists before any deterministic business tool runs.
- Each chain is tool-first. LLMs may classify or polish text, but they do not decide live compliance or inventory truth.
- `output_guard` and `RequestTracer` close every request with compliance-safe output and structured telemetry.

Design constraints:
- Exactly 5 intents are routed.
- Live facts come from deterministic tools, not LLM text generation.
- Session state stays minimal: `last_intent`, `last_state`, `last_budget`, `last_product_ids`.
- LLM use is optional. Without `OPENAI_API_KEY`, the system still runs end to end.

## Where Routing, Tools, State, And Observability Live

| Area | File | Purpose |
|---|---|---|
| Routing | `src/router.py` | `detect_followup()`, `extract_params()`, `classify_intent()` |
| Tools | `src/tools.py` | `hot_picks`, `compliance_filter`, `stock_by_warehouse`, `vendor_validate`, `kb_search` |
| State | `src/state.py` | In-memory session state: `last_intent`, `last_state`, `last_budget`, `last_product_ids` |
| Observability | `src/observability.py` | `RequestTracer`, token estimates, JSONL traces |

Additional core modules:

| File | Purpose |
|---|---|
| `src/graph.py` | LangGraph orchestration and `run_query()` entry point |
| `src/guardrails.py` | `validate_user`, `authorize_tools`, `output_guard`, `redact_for_llm()` |
| `src/chains.py` | Canonical intent chains and tool-call recording |
| `src/data.py` | Seed data loading, product resolution, alternative lookup |
| `src/models.py` | Pydantic schemas, allowlists, business policy |
| `src/settings.py` | Centralized runtime config via `configs.<key>` |
| `src/logging_config.py` | Loguru bootstrap for application logging |
| `main.py` | CLI entry point |

## Configuration

All runtime settings are centralized in `src/settings.py` and exposed through `configs.<key>`.

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | `(none)` | Enables LLM fallback classification and optional response polishing |
| `USE_LLM_FORMATTING` | `false` | Enables optional LLM polishing around deterministic output |
| `LOG_LEVEL` | `INFO` | Application log verbosity |
| `LOG_DIR` | `.logs` | Directory for application and trace logs |
| `LOG_FILE` | `application.log` | Main application log filename |

## Testing

```bash
uv run pytest
```
