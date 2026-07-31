"""
صلاحيات مجموعة «المسوقين» — تُستخدم من setup_permissions.py وأمر sync_marketer_permissions.

بدون هذه الصلاحيات، روابط لوحة «إحصائياتي» إلى /admin/listings/... تعيد 403 Forbidden.
"""
from __future__ import annotations

from typing import Iterable

# أسماء صلاحيات Django (codename) على تطبيق listings
MARKETER_LISTINGS_PERMISSIONS: tuple[str, ...] = (
    # عقارات (عرض الروابط والعقارات المرتبطة)
    "view_property",
    # عملاء محتملون (Kanban + إجراءات)
    "view_propertylead",
    "change_propertylead",
    # طلبات بحث عقار + مسندة للمسوّق
    "view_propertyrequest",
    "change_propertyrequest",
    # مطابقات داخل صفحة الطلب (inline)
    "view_propertymatch",
    # روابط ذكية
    "view_propertysmartlink",
    "add_propertysmartlink",
    "change_propertysmartlink",
    # طلبات سريعة من البطاقة
    "view_fastrequest",
    "change_fastrequest",
)


def sync_marketer_group_permissions(group_name: str = "المسوقين") -> dict:
    """
    تضبط صلاحيات المجموعة لتطابق القائمة أعلاه (استبدال كامل، لا تكرار).
    يعيد: {"group": str, "count": int, "missing": list[str]}
    """
    from django.contrib.auth.models import Group, Permission

    group, _created = Group.objects.get_or_create(name=group_name)
    perms_qs = Permission.objects.filter(
        content_type__app_label="listings",
        codename__in=[*MARKETER_LISTINGS_PERMISSIONS],
    )
    found: Iterable[str] = perms_qs.values_list("codename", flat=True)
    found_set = set(found)
    missing = [c for c in MARKETER_LISTINGS_PERMISSIONS if c not in found_set]

    group.permissions.set(perms_qs)
    return {
        "group": group_name,
        "count": perms_qs.count(),
        "missing": missing,
    }
