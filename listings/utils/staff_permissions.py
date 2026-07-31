"""
صلاحيات مساعدة لموظفي الإدارة (غير superuser): إنشاء مستخدمين وتغيير كلمات المرور.
يُستثنى المستخدم الفائق و PRIMARY_ADMIN_USERNAME من القيود.
عند التبديل كمسوّق (impersonation) تُقيَّم صلاحيات المدير الحقيقي (impersonator).
"""
from __future__ import annotations

from django.conf import settings

from listings.models import UserAccessProfile


def admin_actor(request):
    """المستخدم الفعلي في الجلسة (المدير عند التبديل كمسوّق، وإلا المستخدم الحالي)."""
    imp = getattr(request, "impersonator", None)
    if imp is not None:
        return imp
    return request.user


def _is_primary_admin(user) -> bool:
    name = (getattr(settings, "PRIMARY_ADMIN_USERNAME", None) or "").strip()
    return bool(name and getattr(user, "username", None) == name)


def staff_may_add_users(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or _is_primary_admin(user):
        return True
    try:
        return user.access_profile.allow_add_users
    except UserAccessProfile.DoesNotExist:
        return True


def staff_may_change_passwords(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or _is_primary_admin(user):
        return True
    try:
        return user.access_profile.allow_change_passwords
    except UserAccessProfile.DoesNotExist:
        return True


def staff_may_access_users_groups(user) -> bool:
    """
    وصول قسم Users & Groups محصور بمدير النظام فقط:
    - superuser
    - أو الحساب المرجعي PRIMARY_ADMIN_USERNAME
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return bool(getattr(user, "is_superuser", False) or _is_primary_admin(user))


def staff_is_co_admin(user) -> bool:
    """
    مدير مشارك:
    - مستخدم staff غير superuser
    - وينتمي لإحدى مجموعات المدراء المشاركين المعرفة في الإعدادات.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return False
    default_names = [
        "مجموعة المدراء المشاركين",
        "المدراء المشاركين",
        "المدير المشارك",
        "مدير مشارك",
        "co_admin",
        "co-admin",
    ]
    raw = getattr(settings, "CO_ADMIN_GROUP_NAMES", ",".join(default_names))
    names = set(default_names)
    names.update(x.strip() for x in str(raw).split(",") if x.strip())
    if not names:
        return False
    if user.groups.filter(name__in=list(names)).exists():
        return True

    # مطابقة مرنة: تدعم أسماء مثل "المدراء المشاركين سيرفر محلي"
    # طالما الاسم يحتوي دلالة "مدير/مدراء" + "مشارك".
    def _norm(v: str) -> str:
        return " ".join((v or "").strip().lower().replace("-", " ").replace("_", " ").split())

    for group_name in user.groups.values_list("name", flat=True):
        n = _norm(group_name)
        if ("مدير" in n or "مدراء" in n or "admin" in n) and ("مشارك" in n or "co admin" in n):
            return True
    return False
