"""
End-to-end tests for the 5 demo scenarios from the problem statement.

Verifies:
  Q1: SALES_RECO - correct chain, no blocked products, review flagged
  Q2: COMPLIANCE_CHECK - ground truth status, alternatives if blocked
  Q3: OPS_STOCK - warehouse table returned
  Q4: VENDOR_ONBOARDING - FAIL with correct missing fields
  Q5: FOLLOW_UP - resolved to SALES_RECO (one of 5 intents), basket simulated
"""

import json
import os
import uuid
from pathlib import Path

import pytest

os.environ["USE_LLM_FORMATTING"] = "false"

from src.graph import build_graph, run_query


def _read_last_trace() -> dict:
    """Read the last line from .logs/traces.jsonl and return it as a dict."""
    log_file = Path(".logs/traces.jsonl")
    assert log_file.exists(), ".logs/traces.jsonl does not exist"
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert lines, ".logs/traces.jsonl is empty"
    return json.loads(lines[-1])


@pytest.fixture(scope="module")
def graph():
    return build_graph()


def _run(graph, query, user_type="internal_sales", session_id=None, vendor_submission=None):
    if session_id is None:
        session_id = str(uuid.uuid4())
    return run_query(graph, query, user_type, session_id, vendor_submission=vendor_submission)


# ---------------------------------------------------------------------------
# Q1: SALES_RECO
# ---------------------------------------------------------------------------


class TestSalesReco:
    def test_intent_is_sales_reco(self, graph):
        r = _run(graph, "Give me hot picks for CA under 5000")
        assert r["intent"] == "SALES_RECO"

    def test_uses_keyword_tier(self, graph):
        r = _run(graph, "Give me hot picks for CA under 5000")
        assert r["classification_tier"] == "keyword"

    def test_hot_picks_called(self, graph):
        r = _run(graph, "Give me hot picks for CA under 5000")
        tool_names = [t["name"] for t in r["tool_results"]]
        assert "hot_picks" in tool_names

    def test_compliance_filter_called(self, graph):
        r = _run(graph, "Give me hot picks for CA under 5000")
        tool_names = [t["name"] for t in r["tool_results"]]
        assert "compliance_filter" in tool_names

    def test_no_blocked_products_in_response(self, graph):
        r = _run(graph, "Give me hot picks for CA under 5000")
        assert (
            "blocked" not in r["response_text"].lower() or "[REVIEW" in r["response_text"]
        )  # blocked is ok in REVIEW flag text

    def test_response_contains_products(self, graph):
        r = _run(graph, "Give me hot picks for CA under 5000")
        assert "SKU-" in r["response_text"]
        assert "$" in r["response_text"]

    def test_review_status_flagged(self, graph):
        r = _run(graph, "Give me hot picks for CA under 5000")
        # Mushroom Gummies have lab_report_required - should show REVIEW flag
        assert "REVIEW" in r["response_text"] or "lab report" in r["response_text"].lower()

    def test_not_degraded(self, graph):
        r = _run(graph, "Give me hot picks for CA under 5000")
        assert r["degraded"] is False


# ---------------------------------------------------------------------------
# Q2: COMPLIANCE_CHECK
# ---------------------------------------------------------------------------


class TestComplianceCheck:
    def test_intent_is_compliance_check(self, graph):
        r = _run(graph, "Why is SKU-1003 not available in CA? Suggest alternatives")
        assert r["intent"] == "COMPLIANCE_CHECK"

    def test_compliance_filter_called(self, graph):
        r = _run(graph, "Why is SKU-1003 not available in CA? Suggest alternatives")
        tool_names = [t["name"] for t in r["tool_results"]]
        assert "compliance_filter" in tool_names

    def test_sku_1003_in_ca_shows_review(self, graph):
        # SKU-1003 (THC Beverage) is NOT blocked in CA (blocked in ID, UT)
        # But it has lab_report_required=True -> REVIEW in CA
        r = _run(graph, "Why is SKU-1003 not available in CA? Suggest alternatives")
        assert "REVIEW" in r["response_text"].upper()
        assert "lab" in r["response_text"].lower()

    def test_sku_1003_in_id_shows_blocked(self, graph):
        r = _run(graph, "Is SKU-1003 available in ID?")
        assert "BLOCKED" in r["response_text"].upper()

    def test_alternatives_shown_when_blocked(self, graph):
        r = _run(graph, "Why is SKU-1031 not available in CA?")
        # SKU-1031 Mushroom Gummies blocked in CA, NY
        assert "alternative" in r["response_text"].lower() or "SKU-" in r["response_text"]


# ---------------------------------------------------------------------------
# Q3: OPS_STOCK
# ---------------------------------------------------------------------------


class TestOpsStock:
    def test_intent_is_ops_stock(self, graph):
        r = _run(graph, "How much stock does SKU-1008 have and where?")
        assert r["intent"] == "OPS_STOCK"

    def test_stock_by_warehouse_called(self, graph):
        r = _run(graph, "How much stock does SKU-1008 have and where?")
        tool_names = [t["name"] for t in r["tool_results"]]
        assert "stock_by_warehouse" in tool_names

    def test_warehouse_table_in_response(self, graph):
        r = _run(graph, "How much stock does SKU-1008 have and where?")
        # Response should list warehouses
        assert any(wh in r["response_text"] for wh in ["FL-1", "CA-2", "TX-1", "CA-1", "NY-1"])

    def test_total_qty_in_response(self, graph):
        r = _run(graph, "How much stock does SKU-1008 have and where?")
        assert "Total" in r["response_text"] or "units" in r["response_text"].lower()


# ---------------------------------------------------------------------------
# Q4: VENDOR_ONBOARDING
# ---------------------------------------------------------------------------


class TestVendorOnboarding:
    def test_intent_is_vendor_onboarding(self, graph):
        r = _run(
            graph,
            "I am uploading a product missing Net Wt and no lab report - what do I fix?",
            vendor_submission={"category": "THC Beverage", "lab_report_attached": False},
        )
        assert r["intent"] == "VENDOR_ONBOARDING"

    def test_vendor_validate_called(self, graph):
        r = _run(
            graph,
            "I am uploading a product missing Net Wt and no lab report - what do I fix?",
            vendor_submission={"category": "THC Beverage", "lab_report_attached": False},
        )
        tool_names = [t["name"] for t in r["tool_results"]]
        assert "vendor_validate" in tool_names

    def test_fail_status_shown(self, graph):
        r = _run(
            graph,
            "I am uploading a product missing Net Wt and no lab report",
            vendor_submission={"category": "THC Beverage", "lab_report_attached": False},
        )
        assert "FAIL" in r["response_text"]

    def test_missing_fields_listed(self, graph):
        r = _run(
            graph,
            "I am uploading a product missing Net Wt",
            vendor_submission={"category": "THC Beverage", "lab_report_attached": False},
        )
        assert "net_wt_oz" in r["response_text"] or "Net Wt" in r["response_text"]

    def test_portal_vendor_can_access_vendor_onboarding(self, graph):
        r = _run(
            graph,
            "I want to validate a vendor submission",
            user_type="portal_vendor",
            vendor_submission={
                "name": "Test",
                "category": "Accessories",
                "net_wt_oz": 5.0,
                "net_vol_ml": 100.0,
            },
        )
        assert r["intent"] == "VENDOR_ONBOARDING"
        assert "Access denied" not in r["response_text"]


# ---------------------------------------------------------------------------
# Q5: FOLLOW_UP (basket action)
# ---------------------------------------------------------------------------


class TestFollowUp:
    def test_follow_up_resolves_to_sales_reco(self, graph):
        session_id = "demo-followup-" + str(uuid.uuid4())[:8]
        # First query to populate session
        _run(
            graph,
            "Give me hot picks for CA under 5000",
            session_id=session_id,
            user_type="internal_sales",
        )
        # Follow-up
        r = _run(
            graph,
            "Ok add 2 of the first one to the basket",
            session_id=session_id,
            user_type="internal_sales",
        )
        assert r["intent"] == "SALES_RECO"

    def test_follow_up_intent_not_sixth(self, graph):
        valid = {"SALES_RECO", "COMPLIANCE_CHECK", "VENDOR_ONBOARDING", "OPS_STOCK", "GENERAL_KB"}
        session_id = "demo-followup-" + str(uuid.uuid4())[:8]
        _run(
            graph,
            "Give me hot picks for CA under 5000",
            session_id=session_id,
            user_type="internal_sales",
        )
        r = _run(
            graph,
            "Ok add 2 of the first one to the basket",
            session_id=session_id,
            user_type="internal_sales",
        )
        assert r["intent"] in valid

    def test_basket_simulation_message(self, graph):
        session_id = "demo-followup-" + str(uuid.uuid4())[:8]
        _run(
            graph,
            "Give me hot picks for CA under 5000",
            session_id=session_id,
            user_type="internal_sales",
        )
        r = _run(
            graph,
            "Ok add 2 of the first one to the basket",
            session_id=session_id,
            user_type="internal_sales",
        )
        response = r["response_text"]
        assert "basket" in response.lower() or "Basket simulation" in response

    def test_basket_adds_correct_product(self, graph):
        session_id = "demo-followup-" + str(uuid.uuid4())[:8]
        _run(
            graph,
            "Give me hot picks for CA under 5000",
            session_id=session_id,
            user_type="internal_sales",
        )
        r = _run(
            graph,
            "Ok add 2 of the first one to the basket",
            session_id=session_id,
            user_type="internal_sales",
        )
        # Top product for CA under 5000 is SKU-1016 (Kratom - Pulse 371)
        assert "SKU-1016" in r["response_text"] or "Kratom" in r["response_text"]


# ---------------------------------------------------------------------------
# Permission enforcement
# ---------------------------------------------------------------------------


class TestPermissions:
    def test_portal_vendor_denied_sales_reco(self, graph):
        r = _run(graph, "Give me hot picks for CA under 5000", user_type="portal_vendor")
        assert "Access denied" in r["response_text"]

    def test_portal_customer_denied_vendor_onboarding(self, graph):
        r = _run(graph, "I want to onboard a vendor product", user_type="portal_customer")
        assert "Access denied" in r["response_text"]

    def test_invalid_user_type_rejected(self, graph):
        r = _run(graph, "Give me hot picks", user_type="admin_user")
        assert "Access denied" in r["response_text"] or "denied" in r["response_text"].lower()


# ---------------------------------------------------------------------------
# Full live-demo sequence Q1 -> Q5 (exact order from Problem Statement)
# ---------------------------------------------------------------------------


class TestFullDemoSequence:
    def test_full_demo_sequence_q1_to_q5(self, graph):
        """
        Run the exact demo walkthrough from Problem_Statement.md in order.
        Q1 sales must survive Q2 compliance, Q3 ops, Q4 vendor turns so that
        Q5 basket follow-up resolves 'the first one' to the Q1 top product.
        """
        session_id = "full-demo-" + str(uuid.uuid4())[:8]

        # Q1 - SALES_RECO: populate session with sales product list
        r1 = _run(graph, "Give me hot picks for CA under 5000", session_id=session_id)
        assert r1["intent"] == "SALES_RECO"

        # Q2 - COMPLIANCE_CHECK: must NOT overwrite last_product_ids
        r2 = _run(graph, "Why is SKU-1003 not available in CA?", session_id=session_id)
        assert r2["intent"] == "COMPLIANCE_CHECK"

        # Q3 - OPS_STOCK: must NOT overwrite last_product_ids
        r3 = _run(graph, "How much stock does SKU-1008 have and where?", session_id=session_id)
        assert r3["intent"] == "OPS_STOCK"

        # Q4 - VENDOR_ONBOARDING: must NOT overwrite last_intent or last_product_ids
        r4 = _run(
            graph,
            "I am uploading a product missing Net Wt",
            session_id=session_id,
            vendor_submission={"category": "THC Beverage", "lab_report_attached": False},
        )
        assert r4["intent"] == "VENDOR_ONBOARDING"

        # Q5 - basket follow-up: must resolve to Q1 first product (SKU-1016 / Kratom)
        r5 = _run(graph, "Ok add 2 of the first one to the basket", session_id=session_id)
        assert r5["intent"] == "SALES_RECO", (
            f"Q5 intent should be SALES_RECO but got {r5['intent']!r}. "
            "Check that last_intent and last_product_ids are preserved through Q2-Q4."
        )
        assert "basket" in r5["response_text"].lower(), (
            "Q5 response should contain basket simulation message"
        )
        assert "SKU-1016" in r5["response_text"] or "Kratom" in r5["response_text"], (
            "Q5 should resolve 'first one' to the Q1 top product (SKU-1016 Kratom - Pulse 371)"
        )


# ---------------------------------------------------------------------------
# Observability: request_id must match between API response and trace log
# ---------------------------------------------------------------------------


class TestObservability:
    def test_request_id_matches_trace_log(self, graph):
        """
        The request_id returned by run_query() must equal the request_id
        written to .logs/traces.jsonl. Previously these were two independent
        UUIDs because RequestTracer generated its own.
        """
        r = _run(graph, "Give me hot picks for CA under 5000")
        returned_id = r["request_id"]
        last_trace = _read_last_trace()
        assert last_trace["request_id"] == returned_id, (
            f"Returned request_id {returned_id!r} does not match "
            f"trace log request_id {last_trace['request_id']!r}"
        )


# ---------------------------------------------------------------------------
# PII redaction: redact_for_llm() must strip vendor entity fields
# ---------------------------------------------------------------------------


def test_pii_redaction_removes_vendor_name():
    """
    redact_for_llm() must strip PII keys from vendor submission sub-dict
    while leaving non-PII structural fields intact.
    """
    from src.guardrails import redact_for_llm

    chain_out = {
        "submission": {"name": "ACME Corp", "vendor_id": "V-99", "category": "THC Beverage"},
        "status": "FAIL",
        "missing_fields": ["net_wt_oz"],
    }
    redacted = redact_for_llm(chain_out)

    assert "name" not in redacted["submission"], "vendor name must be redacted"
    assert "vendor_id" not in redacted["submission"], "vendor_id must be redacted"
    assert redacted["submission"]["category"] == "THC Beverage", "category must be preserved"
    assert redacted["status"] == "FAIL", "status must be preserved"
    assert redacted["missing_fields"] == ["net_wt_oz"], "missing_fields must be preserved"
