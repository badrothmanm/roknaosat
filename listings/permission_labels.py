# -*- coding: utf-8 -*-
"""
تسميات موحّدة لصلاحيات Django في واجهة الإدارة (قائمة مزدوجة).
تقليل التشابه مع السلسلة الافتراضية: «app | model | Can add ...»
"""
from __future__ import annotations

from typing import Optional

from django import forms

# تسميات تطبيقات شائعة (مختصرة)
APP_LABELS_AR: dict[str, str] = {
    "auth": "المصادقة",
    "contenttypes": "أنواع المحتوى",
    "sessions": "الجلسات",
    "admin": "لوحة الإدارة",
    "listings": "العقارات والقوائم",
    "market": "البورصة العقارية",
    "sites": "المواقع",
}

# أفعال الصلاحيات الافتراضية لنماذج Django
CODENAME_VERBS_AR: dict[str, str] = {
    "add": "إضافة",
    "change": "تعديل",
    "delete": "حذف",
    "view": "عرض",
}


def _split_default_codename(codename: str) -> tuple[Optional[str], str]:
    """
    يفصل بادئة add/change/delete/view عن الباقي إن وُجدت.
    """
    for prefix in ("add_", "change_", "delete_", "view_"):
        if codename.startswith(prefix):
            return prefix.rstrip("_"), codename[len(prefix) :]
    return None, codename


def readable_permission_label(permission) -> str:
    """
    سطر واحد مقنّن: [التطبيق] الفعل — النموذج
    بدون تكرار «app | model | ...» بنفس شكل Django الافتراضي.
    """
    ct = permission.content_type
    app_label = ct.app_label
    app_ar = APP_LABELS_AR.get(app_label, app_label)

    model_cls = ct.model_class()
    if model_cls is not None:
        try:
            model_name_ar = str(model_cls._meta.verbose_name)
        except Exception:
            model_name_ar = ct.model
    else:
        model_name_ar = ct.model

    codename = permission.codename
    prefix, rest = _split_default_codename(codename)

    if prefix and prefix in CODENAME_VERBS_AR:
        verb_ar = CODENAME_VERBS_AR[prefix]
        # سطر واضح: الفعل + النموذج + التطبيق بين قوسين
        return f"{verb_ar} «{model_name_ar}» [{app_ar}]"

    # صلاحيات مخصّصة أو غير قياسية: الاسم الافتراضي + سياق مختصر
    name = getattr(permission, "name", None) or codename
    return f"{name} — «{model_name_ar}» [{app_ar}]"


def permission_label_from_instance(obj) -> str:
    """للاستخدام مع ModelMultipleChoiceField.label_from_instance"""
    return readable_permission_label(obj)


class ReadablePermissionMultipleChoiceField(forms.ModelMultipleChoiceField):
    """
    Django 6+: لا يُمرَّر label_from_instance كـ kwargs إلى الحقل؛
    يُعرَّف كدالة على الفئة الفرعية.
    """

    def label_from_instance(self, obj):
        return readable_permission_label(obj)
