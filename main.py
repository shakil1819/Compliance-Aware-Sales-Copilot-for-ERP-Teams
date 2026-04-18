"""
CLI entry point.
Run: uv run main.py

Prompts for user_type, then enters a chat loop.
Type 'quit' or 'exit' to stop.
Type 'vendor: <json>' to pass a vendor submission alongside a query.
"""

from __future__ import annotations

import json
import uuid

from src.graph import build_graph, run_query
from src.logging_config import logger, setup_logging
from src.settings import configs

_USER_TYPES = ["internal_sales", "portal_vendor", "portal_customer"]


def _pick_user_type() -> str:
    print("\nUser types:")
    for i, ut in enumerate(_USER_TYPES, 1):
        print(f"  {i}. {ut}")
    while True:
        choice = input("Select user type [1-3]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(_USER_TYPES):
            return _USER_TYPES[int(choice) - 1]
        print("  Invalid choice, try again.")


def main() -> None:
    setup_logging()
    logger.info("Starting {} in {} mode", configs.app_name, configs.environment)

    print("=== AI Chat Service PoC ===")
    print("Building graph and loading data...")

    graph = build_graph()

    user_type = _pick_user_type()
    session_id = str(uuid.uuid4())

    print(f"\nSession started [{user_type}] (session_id: {session_id[:8]}...)")
    print("Type your query. Use 'quit' to exit.")
    print("Vendor submission hint: prefix with 'VENDOR_JSON:' then JSON, e.g.:")
    print(
        '  VENDOR_JSON:{"category":"THC Beverage","net_wt_oz":12} '
        "I have a product missing net vol\n"
    )

    while True:
        try:
            raw = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            logger.info("Interactive session interrupted by user")
            print("\nExiting.")
            break

        if not raw:
            continue
        if raw.lower() in ("quit", "exit", "q"):
            logger.info("Interactive session ended by user command")
            print("Goodbye.")
            break

        # Optional vendor submission prefix
        vendor_submission: dict | None = None
        query = raw
        if raw.upper().startswith("VENDOR_JSON:"):
            try:
                rest = raw[len("VENDOR_JSON:") :]
                brace_end = rest.index("}") + 1
                vendor_submission = json.loads(rest[:brace_end])
                query = rest[brace_end:].strip()
                if not query:
                    query = "Validate this vendor submission"
            except (ValueError, json.JSONDecodeError) as e:
                logger.error("Failed to parse VENDOR_JSON payload: {}", e)
                print(f"  [!] Could not parse VENDOR_JSON: {e}")
                continue

        try:
            result = run_query(
                graph=graph,
                user_query=query,
                user_type=user_type,
                session_id=session_id,
                vendor_submission=vendor_submission,
            )
        except Exception as exc:
            logger.exception("Unhandled CLI query execution error: {}", exc)
            print(f"  [ERROR] {exc}")
            continue

        logger.info(
            "CLI response intent={} degraded={} request_id={}",
            result.get("intent", "?"),
            result.get("degraded"),
            result.get("request_id"),
        )
        print(f"\nAssistant [{result.get('intent', '?')}]:")
        print(result["response_text"])
        if result.get("degraded"):
            print(f"\n  [!] DEGRADED: {result.get('degraded_reason')}")
        print()


if __name__ == "__main__":
    main()
