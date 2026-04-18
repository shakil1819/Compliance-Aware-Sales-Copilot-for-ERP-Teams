"""
In-memory data layer. Parses seed_data.json once at startup.
All tools and chain helpers read from this module - no SQLite, no re-reads.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.models import Product, InventoryEntry, Customer, Vendor, KBDoc

# ---------------------------------------------------------------------------
# Module-level store - populated by load_seed_data()
# ---------------------------------------------------------------------------

_products: list[Product] = []
_inventory: list[InventoryEntry] = []
_customers: list[Customer] = []
_vendors: list[Vendor] = []
_kb_docs: list[KBDoc] = []

# Lookup indices built on load
_products_by_id: dict[int, Product] = {}
_products_by_sku: dict[str, Product] = {}

_loaded = False


def load_seed_data(path: str = "data/seed_data (3).json") -> None:
    """Parse seed_data.json into typed Python objects. Call once at startup."""
    global _loaded
    if _loaded:
        return

    raw = json.loads(Path(path).read_text(encoding="utf-8"))

    global _products, _inventory, _customers, _vendors, _kb_docs
    global _products_by_id, _products_by_sku

    _products  = [Product(**p) for p in raw["products"]]
    _inventory = [InventoryEntry(**i) for i in raw["inventory"]]
    _customers = [Customer(**c) for c in raw["customers"]]
    _vendors   = [Vendor(**v) for v in raw["vendors"]]
    _kb_docs   = [KBDoc(**d) for d in raw["kb_docs"]]

    _products_by_id  = {p.product_id: p for p in _products}
    _products_by_sku = {p.sku: p for p in _products}

    _loaded = True


# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------

def get_products() -> list[Product]:
    return _products


def get_inventory() -> list[InventoryEntry]:
    return _inventory


def get_customers() -> list[Customer]:
    return _customers


def get_vendors() -> list[Vendor]:
    return _vendors


def get_kb_docs() -> list[KBDoc]:
    return _kb_docs


def get_product_by_id(product_id: int) -> Product | None:
    return _products_by_id.get(product_id)


def get_product_by_sku(sku: str) -> Product | None:
    return _products_by_sku.get(sku)


# ---------------------------------------------------------------------------
# Chain helpers (not tools - internal use only, not in allowlists)
# ---------------------------------------------------------------------------

def resolve_product(sku_or_name: str) -> Product | None:
    """
    Resolve a product reference.
    1. Exact SKU match (SKU-XXXX).
    2. Case-insensitive substring match on product name.
    Returns the first match or None.
    """
    # Exact SKU
    by_sku = get_product_by_sku(sku_or_name.upper())
    if by_sku:
        return by_sku

    # Name substring (case-insensitive)
    query_lower = sku_or_name.lower()
    for p in _products:
        if query_lower in p.name.lower():
            return p

    return None


def find_alternatives(
    category: str,
    state: str,
    exclude_ids: list[int],
    limit: int = 5,
) -> list[Product]:
    """
    Return top-N products in the same category that are allowed in state,
    sorted by popularity descending. Excludes specified product IDs.
    """
    candidates = [
        p for p in _products
        if p.category == category
        and p.product_id not in exclude_ids
        and state not in p.blocked_states
    ]
    candidates.sort(key=lambda p: p.popularity_score, reverse=True)
    return candidates[:limit]
