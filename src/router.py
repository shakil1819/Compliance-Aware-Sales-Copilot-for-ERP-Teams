"""
Intent classification - three separate, independently testable functions.

1. detect_followup(query, session_state) -> (is_followup, last_intent)
2. extract_params(query) -> ExtractedParams
3. classify_intent(query) -> IntentClassification

Follow-up is a pre-router step, NOT a 6th intent.
Classification always returns exactly one of the 5 required intents.
"""

from __future__ import annotations

import re
from typing import Optional

from langsmith import traceable  # type: ignore[import]

from src.logging_config import logger
from src.models import ExtractedParams, IntentClassification, VALID_INTENTS
from src.settings import configs
from src.state import SessionState

# ---------------------------------------------------------------------------
# US state codes - hardcoded set prevents false matches on common words
# ---------------------------------------------------------------------------

US_STATES: set[str] = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}

# ---------------------------------------------------------------------------
# Keyword sets per intent (multi-word phrases scored as single tokens)
# ---------------------------------------------------------------------------

KEYWORD_SETS: dict[str, list[str]] = {
    "SALES_RECO": [
        "hot picks", "hot pick", "recommend", "recommendation", "suggest",
        "best sellers", "best seller", "top products", "top product",
        "under $", "budget", "popular", "top picks", "what's hot",
        "show me products", "give me", "find me",
    ],
    "COMPLIANCE_CHECK": [
        "blocked", "not available", "why can't", "why is", "legal",
        "compliance", "banned", "restricted", "available in", "can i sell",
        "is it legal", "is it available", "alternatives", "alternative",
        "not sell", "cannot sell", "not allowed", "why not",
    ],
    "VENDOR_ONBOARDING": [
        "vendor", "onboard", "upload", "catalog", "missing fields",
        "lab report", "net wt", "net weight", "net vol", "submission",
        "uploading", "product upload", "onboarding", "what do i fix",
        "what to fix", "missing", "required fields",
    ],
    "OPS_STOCK": [
        "stock", "warehouse", "inventory", "how much", "quantity",
        "where is", "available qty", "qty", "on hand", "in stock",
        "how many", "where can i", "warehouses",
    ],
    "GENERAL_KB": [
        "return", "returns", "shipping", "policy", "sop", "how do i",
        "what is the process", "procedure", "guide", "documentation",
        "restocking", "delivery", "freight",
    ],
}

# Follow-up reference patterns
_FOLLOWUP_PATTERNS = [
    r"\bthe first one\b",
    r"\bthe second one\b",
    r"\bthe third one\b",
    r"\bthat product\b",
    r"\badd \d+\b",
    r"\badd to (basket|cart)\b",
    r"\bbasket\b",
    r"\bcart\b",
    r"\bthose\b",
    r"\bthe (first|second|third|last)\b",
]
_FOLLOWUP_RE = re.compile("|".join(_FOLLOWUP_PATTERNS), re.IGNORECASE)

# Ordinal reference -> 0-based index
_ORDINAL_MAP = {"first": 0, "second": 1, "third": 2, "last": -1}
_ORDINAL_RE = re.compile(r"\b(first|second|third|last)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# 1. detect_followup
# ---------------------------------------------------------------------------

@traceable(run_type="chain", name="detect_followup")
def detect_followup(
    query: str,
    session: Optional[SessionState],
) -> tuple[bool, Optional[str]]:
    """
    Detect if this query is a follow-up referencing a prior result.

    Returns:
        (True, last_intent)  if follow-up detected AND session has prior product IDs
        (False, None)        otherwise
    """
    if not _FOLLOWUP_RE.search(query):
        return False, None

    if session is None or not session.last_product_ids or not session.last_intent:
        # Pattern matched but no session context - force fresh classification
        return False, None

    if session.last_intent not in VALID_INTENTS:
        return False, None

    return True, session.last_intent


# ---------------------------------------------------------------------------
# 2. extract_params
# ---------------------------------------------------------------------------

@traceable(run_type="chain", name="extract_params")
def extract_params(query: str) -> ExtractedParams:
    """
    Extract structured parameters from raw query text.
    State matching uses the hardcoded US_STATES set (not raw regex) to
    prevent false positives on common words like IN, OR, IS, etc.
    """
    params = ExtractedParams()

    # State: match 2-letter uppercase tokens against US_STATES.
    # Only uppercase to avoid false positives on common words (in, or, me, ok).
    for token in re.findall(r"\b([A-Z]{2})\b", query):
        if token in US_STATES:
            params.state = token
            break

    # Budget: "$5000", "under 5000", "under $5,000"
    # Strip out any SKU-prefixed numbers first to prevent false budget matches
    budget_query = re.sub(r"\bSKU-\d+\b", "", query, flags=re.IGNORECASE)
    budget_match = re.search(
        r"under\s+\$?([\d,]+(?:\.\d+)?)|^\$?([\d,]+(?:\.\d+)?)\s*(?:budget|dollars?|usd)",
        budget_query,
        re.IGNORECASE,
    )
    if budget_match:
        raw_val = budget_match.group(1) or budget_match.group(2)
        if raw_val:
            try:
                params.budget = float(raw_val.replace(",", ""))
            except ValueError:
                pass

    # SKU: SKU-XXXX (exact pattern)
    sku_match = re.search(r"\b(SKU-\d+)\b", query, re.IGNORECASE)
    if sku_match:
        params.sku = sku_match.group(1).upper()

    # Quantity: require explicit context - "add 2 of", "2 units", "qty 3", "order 5"
    qty_match = re.search(
        r"\b(?:add|qty|quantity|order)\s+(\d+)\b"
        r"|(\d+)\s+(?:units?|pcs?|pieces?|cases?)",
        query,
        re.IGNORECASE,
    )
    if qty_match:
        raw_qty = qty_match.group(1) or qty_match.group(2)
        try:
            params.quantity = int(raw_qty)
        except (ValueError, TypeError):
            pass

    # Ordinal reference for follow-ups
    ord_match = _ORDINAL_RE.search(query)
    if ord_match:
        params.ordinal_ref = _ORDINAL_MAP.get(ord_match.group(1).lower(), 0)

    return params


# ---------------------------------------------------------------------------
# 3. classify_intent
# ---------------------------------------------------------------------------

def _score_all_intents(query: str) -> dict[str, float]:
    """Return keyword overlap score for each intent (0.0 - 1.0)."""
    query_lower = query.lower()
    scores: dict[str, float] = {}
    for intent, keywords in KEYWORD_SETS.items():
        hits = sum(1 for kw in keywords if kw in query_lower)
        scores[intent] = hits / max(len(keywords), 1)
    return scores


@traceable(run_type="chain", name="classify_intent")
def classify_intent(
    query: str,
    confidence_threshold: float = 0.05,
) -> IntentClassification:
    """
    Two-tier intent classifier.

    Tier-1: keyword scoring (free, <1ms).
    Tier-2: LLM structured output fallback (requires OPENAI_API_KEY).

    On LLM failure: use best keyword score even if below threshold, with
    low_confidence=True. If no keyword signal at all, raises ClassificationError.
    """
    scores = _score_all_intents(query)
    best_intent = max(scores, key=lambda k: scores[k])
    best_score = scores[best_intent]

    # Tier-1: confident keyword match
    if best_score >= confidence_threshold:
        return IntentClassification(
            intent=best_intent,  # type: ignore[arg-type]
            confidence=round(best_score, 4),
            tier="keyword",
            low_confidence=best_score < 0.1,
        )

    # Tier-2: LLM fallback (only if API key present)
    if configs.openai_api_key:
        try:
            result = _llm_classify(query)
            return result
        except Exception as exc:
            logger.warning("LLM classification failed: {}", exc)

    # Fallback: use best keyword score even if weak
    if best_score > 0:
        return IntentClassification(
            intent=best_intent,  # type: ignore[arg-type]
            confidence=round(best_score, 4),
            tier="keyword",
            low_confidence=True,
        )

    # No signal at all - fail closed
    raise ClassificationError(
        f"Cannot classify query - no keyword signal and LLM unavailable: {query!r}"
    )


@traceable(run_type="llm", name="llm_classify")
def _llm_classify(query: str) -> IntentClassification:
    """Call OpenAI with structured output to classify the intent."""
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        timeout=30,
        max_tokens=100,
        api_key=configs.openai_api_key,
    )
    structured = llm.with_structured_output(IntentClassification)

    prompt = (
        "Classify this user query into exactly one intent.\n"
        "Intents:\n"
        "  SALES_RECO - product recommendations, hot picks, suggest products\n"
        "  COMPLIANCE_CHECK - legality, blocked, not available, alternatives\n"
        "  VENDOR_ONBOARDING - vendor product upload, validation, missing fields\n"
        "  OPS_STOCK - inventory, warehouse quantities, stock levels\n"
        "  GENERAL_KB - policies, SOPs, returns, shipping, general questions\n\n"
        f"Query: {query}\n\n"
        "Return the intent and confidence (0-1)."
    )

    result = structured.invoke(prompt)
    result.tier = "llm"
    return result


class ClassificationError(RuntimeError):
    """Raised when classification fails and no fallback is available."""
