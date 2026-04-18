"""
Unit tests for all 5 deterministic tools.
Covers: allowed, blocked, review compliance statuses; PASS/REVIEW/FAIL vendor validation;
        stock lookups; kb visibility; hot_picks budget/state filtering.
"""

import pytest
from src.data import load_seed_data
from src.tools import hot_picks, compliance_filter, stock_by_warehouse, vendor_validate, kb_search
from src.models import VendorSubmission


@pytest.fixture(autouse=True, scope="module")
def _load():
    load_seed_data()


# ---------------------------------------------------------------------------
# hot_picks
# ---------------------------------------------------------------------------

class TestHotPicks:
    def test_returns_at_most_limit(self):
        results = hot_picks("CA", 10000, limit=5)
        assert len(results) <= 5

    def test_sorted_by_popularity_desc(self):
        results = hot_picks("CA", 10000, limit=10)
        scores = [p.popularity_score for p in results]
        assert scores == sorted(scores, reverse=True)

    def test_budget_filter(self):
        results = hot_picks("CA", 30.0)
        assert all(p.price <= 30.0 for p in results)

    def test_state_filter_blocks_products(self):
        # SKU-1002 is a Nicotine Vape blocked in MA
        results = hot_picks("MA", 10000)
        skus = [p.sku for p in results]
        assert "SKU-1002" not in skus

    def test_zero_budget_returns_empty(self):
        results = hot_picks("CA", 0.0)
        assert results == []

    def test_unknown_state_no_products_blocked_by_it(self):
        # ZZ is not a valid state in any blocked_states list, so no filtering occurs
        results = hot_picks("ZZ", 10000)
        assert len(results) > 0


# ---------------------------------------------------------------------------
# compliance_filter
# ---------------------------------------------------------------------------

class TestComplianceFilter:
    def test_allowed_status(self):
        # SKU-1001 (Accessories) - no blocked_states, no lab required
        results = compliance_filter("CA", [1001])
        assert len(results) == 1
        assert results[0].status == "allowed"
        assert results[0].reason_code == ""

    def test_blocked_status(self):
        # SKU-1003 (THC Beverage) blocked in ID, UT
        results = compliance_filter("ID", [1003])
        assert results[0].status == "blocked"
        assert "thc" in results[0].reason_code.lower()
        assert "ID" in results[0].reason_code

    def test_review_status_lab_report(self):
        # SKU-1004 (Mushroom Gummies) - lab_report_required=True, not blocked in CA
        results = compliance_filter("CA", [1004])
        assert results[0].status == "review"
        assert "lab report" in results[0].reason_code.lower()

    def test_multiple_products(self):
        # Mix of statuses
        results = compliance_filter("ID", [1001, 1003, 1004])
        statuses = {r.product_id: r.status for r in results}
        assert statuses[1001] == "allowed"    # Accessories, no restrictions
        assert statuses[1003] == "blocked"    # THC blocked in ID
        assert statuses[1004] == "review"     # Lab required, not blocked in ID

    def test_unknown_product_returns_review(self):
        results = compliance_filter("CA", [99999])
        assert results[0].status == "review"
        assert "not found" in results[0].reason_code.lower()

    def test_skus_present_in_result(self):
        results = compliance_filter("CA", [1003])
        assert results[0].sku == "SKU-1003"
        assert results[0].name != ""


# ---------------------------------------------------------------------------
# stock_by_warehouse
# ---------------------------------------------------------------------------

class TestStockByWarehouse:
    def test_known_product_has_warehouses(self):
        result = stock_by_warehouse(1008)
        assert result.product_id == 1008
        assert result.sku == "SKU-1008"
        assert len(result.warehouses) > 0
        assert result.total_qty > 0

    def test_total_qty_equals_sum_of_warehouses(self):
        result = stock_by_warehouse(1008)
        expected = sum(w.qty for w in result.warehouses)
        assert result.total_qty == expected

    def test_product_without_inventory(self):
        # Arbitrary high ID likely has no inventory rows
        result = stock_by_warehouse(99999)
        assert result.total_qty == 0
        assert result.warehouses == []


# ---------------------------------------------------------------------------
# vendor_validate
# ---------------------------------------------------------------------------

class TestVendorValidate:
    def test_pass_all_fields_with_lab_report(self):
        sub = VendorSubmission(
            name="Test Product",
            category="THC Beverage",
            net_wt_oz=10.0,
            net_vol_ml=300.0,
            lab_report_attached=True,
        )
        result = vendor_validate(sub)
        assert result.status == "PASS"
        assert result.missing_fields == []
        assert result.required_documents == []

    def test_review_missing_lab_report(self):
        sub = VendorSubmission(
            name="Test Product",
            category="THC Beverage",
            net_wt_oz=10.0,
            net_vol_ml=300.0,
            lab_report_attached=False,
        )
        result = vendor_validate(sub)
        assert result.status == "REVIEW"
        assert "lab_report" in result.required_documents
        assert result.missing_fields == []

    def test_fail_missing_required_fields(self):
        sub = VendorSubmission(
            name="Test Product",
            category="THC Beverage",
            # net_wt_oz and net_vol_ml missing
            lab_report_attached=False,
        )
        result = vendor_validate(sub)
        assert result.status == "FAIL"
        assert "net_wt_oz" in result.missing_fields
        assert "net_vol_ml" in result.missing_fields

    def test_fail_no_name(self):
        sub = VendorSubmission(
            category="Accessories",
            net_wt_oz=5.0,
            net_vol_ml=100.0,
        )
        result = vendor_validate(sub)
        assert result.status == "FAIL"
        assert "name" in result.missing_fields

    def test_accessories_no_lab_required(self):
        sub = VendorSubmission(
            name="Test Accessory",
            category="Accessories",
            net_wt_oz=5.0,
            net_vol_ml=100.0,
            lab_report_attached=False,
        )
        result = vendor_validate(sub)
        assert result.status == "PASS"
        assert result.required_documents == []

    def test_mushroom_gummies_require_lab(self):
        sub = VendorSubmission(
            name="Mushroom Product",
            category="Mushroom Gummies",
            net_wt_oz=5.0,
            net_vol_ml=100.0,
            lab_report_attached=False,
        )
        result = vendor_validate(sub)
        assert result.status == "REVIEW"
        assert "lab_report" in result.required_documents


# ---------------------------------------------------------------------------
# kb_search
# ---------------------------------------------------------------------------

class TestKBSearch:
    def test_internal_sales_sees_all_docs(self):
        results = kb_search("return policy shipping vendor", "internal_sales", top_k=10)
        doc_ids = {r.doc_id for r in results}
        assert "SOP-RETURNS" in doc_ids
        assert "POLICY-SHIPPING" in doc_ids
        assert "SOP-VENDOR-UPLOAD" in doc_ids

    def test_portal_customer_limited_visibility(self):
        results = kb_search("vendor upload catalog", "portal_customer", top_k=10)
        for r in results:
            assert r.visibility == "public", f"{r.doc_id} is not public-visible"

    def test_portal_vendor_can_see_vendor_docs(self):
        results = kb_search("vendor upload", "portal_vendor", top_k=10)
        doc_ids = {r.doc_id for r in results}
        assert "SOP-VENDOR-UPLOAD" in doc_ids

    def test_returns_top_k(self):
        results = kb_search("any query", "internal_sales", top_k=2)
        assert len(results) <= 2

    def test_keyword_ranking(self):
        results = kb_search("return", "internal_sales", top_k=3)
        # SOP-RETURNS should rank highest for "return"
        assert results[0].doc_id == "SOP-RETURNS"
