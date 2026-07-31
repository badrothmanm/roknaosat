"""
Lead scoring + duplicate detection helpers for PropertyRequest (unified API + legacy form).

Keeps business logic out of views/serializers for easier testing and tuning.
"""
from __future__ import annotations

import os
import re
from decimal import Decimal
from typing import Optional, Tuple

from django.conf import settings
from django.utils.html import strip_tags

# --- XSS / text hygiene (API inputs; stored text is tag-stripped, not HTML-escaped) ---


def sanitize_text_input(value: Optional[str], *, max_length: Optional[int] = None) -> str:
    """
    Strip HTML tags and collapse whitespace. Mitigates stored XSS if notes/name are ever
    rendered unsafely; prefer always escaping on output in templates.
    """
    if value is None:
        return ""
    text = str(value).strip()
    text = strip_tags(text)
    text = re.sub(r"\s+", " ", text).strip()
    if max_length is not None and len(text) > max_length:
        text = text[:max_length]
    return text


def mask_phone_for_log(phone: str) -> str:
    """Last 4 digits only — avoids logging full PII."""
    p = re.sub(r"\D", "", phone or "")
    if len(p) < 4:
        return "****"
    return f"***{p[-4:]}"


# --- Duplicate fingerprint: phone + property_type + district + budget ---


def find_duplicate_property_request(
    *,
    phone: str,
    property_type: str,
    district: str,
    budget: Optional[Decimal],
):
    """
    Same logical request = same phone, type, district, and budget (including both NULL).
    Uses a single indexed query (see migration composite index).
    """
    from listings.models import PropertyRequest

    qs = PropertyRequest.objects.filter(
        phone=phone,
        property_type=property_type,
        district=district,
    )
    if budget is None:
        qs = qs.filter(budget__isnull=True)
    else:
        qs = qs.filter(budget=budget)
    return qs.order_by("-created_at").only("id", "matched_count", "created_at").first()


# --- Lead score + priority ---

def _prime_district_normalized() -> frozenset:
    """Lowercased district names considered «prime» — override via settings or env."""
    custom = getattr(settings, "LEAD_SCORING_PRIME_DISTRICTS", None)
    if custom is not None:
        return frozenset(str(x).strip().lower() for x in custom if str(x).strip())
    raw = os.getenv("LEAD_SCORING_PRIME_DISTRICTS", "")
    if raw.strip():
        return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())
    # Default: popular Jeddah districts (Arabic names as stored in forms)
    return frozenset(
        {
            "الشاطئ",
            "الروضة",
            "الصفا",
            "أبحر",
            "الكورنيش",
            "الحمراء",
            "الزهراء",
            "النعيم",
            "السلامة",
            "الفيصلية",
            "الكامل",
            "البحيرة",
            "الواحة",
            "السلام",
            "الصفوة",
        }
    )


def compute_lead_score_and_priority(
    *,
    budget: Optional[Decimal],
    district: str,
    rooms: Optional[int],
    furnished: Optional[bool],
    category: Optional[str],
    notes: Optional[str],
    conversation_id: Optional[str],
    name: str,
) -> Tuple[float, str]:
    """
    Heuristic 0–100 score + priority band.
    Tuned via settings.LEAD_SCORING_WEIGHTS when present.
    """
    w = getattr(settings, "LEAD_SCORING_WEIGHTS", None) or {}
    w_budget_cap = float(w.get("BUDGET_CAP", 35))
    w_budget_ref = float(w.get("BUDGET_REF_SAR", 2_000_000))
    w_prime = float(w.get("PRIME_DISTRICT", 25))
    w_rooms = float(w.get("ROOMS", 10))
    w_furnished = float(w.get("FURNISHED", 5))
    w_category = float(w.get("CATEGORY", 5))
    w_notes = float(w.get("NOTES", 10))
    w_conv = float(w.get("CONVERSATION_ID", 5))
    w_name = float(w.get("NAME", 5))
    high_min = float(w.get("PRIORITY_HIGH_MIN", 65))
    med_min = float(w.get("PRIORITY_MEDIUM_MIN", 35))

    score = 0.0

    if budget is not None and budget > 0:
        score += min(w_budget_cap, float(budget) / w_budget_ref * w_budget_cap)

    d_norm = (district or "").strip().lower()
    if d_norm in _prime_district_normalized():
        score += w_prime

    comp = 0.0
    if rooms is not None:
        comp += w_rooms
    if furnished is not None:
        comp += w_furnished
    if category:
        comp += w_category
    if notes and len(notes.strip()) > 15:
        comp += w_notes
    if conversation_id and str(conversation_id).strip():
        comp += w_conv
    if name and len(name.strip()) > 2:
        comp += w_name
    score += min(40.0, comp)

    score = min(100.0, round(score, 2))

    if score >= high_min:
        priority = "high"
    elif score >= med_min:
        priority = "medium"
    else:
        priority = "low"

    return score, priority
