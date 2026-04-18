"""
Tests for the three router functions:
  - detect_followup
  - extract_params
  - classify_intent (keyword tier)
"""

import pytest

from src.data import load_seed_data
from src.router import classify_intent, detect_followup, extract_params
from src.state import SessionState


@pytest.fixture(autouse=True, scope="module")
def _load():
    load_seed_data()


# ---------------------------------------------------------------------------
# detect_followup
# ---------------------------------------------------------------------------


class TestDetectFollowup:
    def _session(self, **kw):
        defaults = {
            "last_intent": "SALES_RECO",
            "last_product_ids": [1016, 1011, 1020],
            "last_state": "CA",
            "last_budget": 5000.0,
        }
        defaults.update(kw)
        return SessionState(**defaults)

    def test_basket_action_detected(self):
        sess = self._session()
        is_f, intent = detect_followup("add 2 of the first one to the basket", sess)
        assert is_f is True
        assert intent == "SALES_RECO"

    def test_the_first_one_detected(self):
        sess = self._session()
        is_f, intent = detect_followup("the first one please", sess)
        assert is_f is True

    def test_no_session_returns_false(self):
        is_f, intent = detect_followup("add 2 of the first one to the basket", None)
        assert is_f is False

    def test_empty_product_ids_returns_false(self):
        sess = self._session(last_product_ids=[])
        is_f, _ = detect_followup("add the first one to basket", sess)
        assert is_f is False

    def test_no_pattern_match_returns_false(self):
        sess = self._session()
        is_f, _ = detect_followup("Give me hot picks for CA under 5000", sess)
        assert is_f is False

    def test_invalid_last_intent_returns_false(self):
        sess = self._session(last_intent="FOLLOW_UP")
        is_f, _ = detect_followup("add 2 of the first one", sess)
        assert is_f is False


# ---------------------------------------------------------------------------
# extract_params
# ---------------------------------------------------------------------------


class TestExtractParams:
    def test_state_uppercase(self):
        p = extract_params("Give me hot picks for CA under 5000")
        assert p.state == "CA"

    def test_state_not_false_positive(self):
        # "IN" in "in CA" should not match "IN" (Indiana) before "CA"
        p = extract_params("What is available in CA?")
        assert p.state == "CA"

    def test_budget_under(self):
        p = extract_params("under 5000 budget please")
        assert p.budget == 5000.0

    def test_sku_extracted(self):
        p = extract_params("Why is SKU-1003 not available in CA?")
        assert p.sku == "SKU-1003"

    def test_sku_does_not_create_budget(self):
        p = extract_params("Why is SKU-1003 not available in CA?")
        assert p.budget is None

    def test_ordinal_first(self):
        p = extract_params("add 2 of the first one to basket")
        assert p.ordinal_ref == 0

    def test_ordinal_second(self):
        p = extract_params("add the second one please")
        assert p.ordinal_ref == 1

    def test_quantity_from_add(self):
        p = extract_params("add 3 of them to cart")
        assert p.quantity == 3

    def test_no_params_in_generic_query(self):
        p = extract_params("what is the return policy?")
        assert p.state is None
        assert p.budget is None
        assert p.sku is None


# ---------------------------------------------------------------------------
# classify_intent (keyword tier only - no LLM)
# ---------------------------------------------------------------------------


class TestClassifyIntent:
    def test_sales_reco(self):
        r = classify_intent("Give me hot picks for CA under 5000")
        assert r.intent == "SALES_RECO"
        assert r.tier == "keyword"

    def test_compliance_check(self):
        r = classify_intent("Why is SKU-1003 not available in CA? Suggest alternatives")
        assert r.intent == "COMPLIANCE_CHECK"

    def test_ops_stock(self):
        r = classify_intent("How much stock does SKU-1008 have and where?")
        assert r.intent == "OPS_STOCK"

    def test_vendor_onboarding(self):
        r = classify_intent("uploading a product missing Net Wt and no lab report")
        assert r.intent == "VENDOR_ONBOARDING"

    def test_general_kb(self):
        r = classify_intent("what is the return policy?")
        assert r.intent == "GENERAL_KB"

    def test_shipping_kb(self):
        r = classify_intent("what is the shipping policy?")
        assert r.intent == "GENERAL_KB"

    def test_returns_exactly_one_of_five_intents(self):
        valid = {"SALES_RECO", "COMPLIANCE_CHECK", "VENDOR_ONBOARDING", "OPS_STOCK", "GENERAL_KB"}
        queries = [
            "hot picks",
            "is this blocked in CA?",
            "inventory for SKU-1001",
            "vendor upload requirements",
            "return policy",
        ]
        for q in queries:
            r = classify_intent(q)
            assert r.intent in valid, f"Bad intent {r.intent!r} for query {q!r}"
