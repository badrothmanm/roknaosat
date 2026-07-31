"""
تطبيع جسم JSON القادم من n8n / أدوات خارجية قبل إنشاء PropertyRequest.

يحوّل أسماء حقول شائعة (camelCase / مرادفات) إلى الحقول التي يتوقعها الـ serializer.
"""
from __future__ import annotations

from typing import Any, Mapping


def _first_non_empty(d: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def normalize_n8n_property_request_payload(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """
    يُرجع نسخة قابلة للتعديل من raw مع:
    - دمج المفاتيح البديلة في الأسماء الرسمية
    - افتراض source=ai_chat و category=family إن وُجدت القيم الأساسية ولم تُحدَّد
    """
    if not raw:
        return {}
    out = dict(raw)

    # --- مرادفات شائعة من واجهات / LLM / n8n ---
    alias_pairs: list[tuple[str, str]] = [
        ("property_type", "propertyType"),
        ("property_type", "type"),
        ("district", "neighborhood"),
        ("district", "area_name"),
        ("budget", "price"),
        ("budget", "max_budget"),
        ("name", "client_name"),
        ("name", "full_name"),
        ("phone", "mobile"),
        ("phone", "phone_number"),
        ("notes", "message"),
        ("notes", "user_message"),
        ("notes", "details"),
        ("conversation_id", "session_id"),
        ("conversation_id", "chat_id"),
    ]
    for canonical, alt in alias_pairs:
        if canonical not in out or out[canonical] in (None, ""):
            v = _first_non_empty(out, (alt,))
            if v is not None and v != "":
                out[canonical] = v

    # ملاحظات من حقول نصية طويلة شائعة
    if not (out.get("notes") or "").strip():
        for k in ("description", "summary", "request_text"):
            v = out.get(k)
            if isinstance(v, str) and v.strip():
                out["notes"] = v.strip()
                break

    # افتراضات مناسبة لمسار المساعد الذكي / n8n
    out.setdefault("source", "ai_chat")
    out.setdefault("category", "family")

    return out
