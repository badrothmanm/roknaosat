"""
ترتيب حسابات staff في القوائم: المدير أولاً، ثم المسوّق المرجعي الأول (مثل b1)، ثم البقية.
"""
from __future__ import annotations

from django.db.models import Case, IntegerField, QuerySet, Value, When


def annotate_staff_marketer_sort(qs: QuerySet, settings_module=None) -> QuerySet:
    """
    يضيف حقل ترتيب _ord ثم يرتّب: PRIMARY_ADMIN_USERNAME → PRIMARY_MARKETER_USERNAME → الآخرون.
    """
    from django.conf import settings as dj_settings

    s = settings_module or dj_settings
    primary = (getattr(s, "PRIMARY_ADMIN_USERNAME", None) or "").strip()
    first_m = (getattr(s, "PRIMARY_MARKETER_USERNAME", None) or "").strip()

    if not primary and not first_m:
        return qs.order_by("username")

    whens = []
    n = 0
    if primary:
        whens.append(When(username=primary, then=Value(n)))
        n += 1
    if first_m and first_m != primary:
        whens.append(When(username=first_m, then=Value(n)))
        n += 1

    return qs.annotate(
        _ord=Case(*whens, default=Value(n), output_field=IntegerField()),
    ).order_by("_ord", "username")
