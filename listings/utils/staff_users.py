"""
مستخدمو staff / الإدارة — إسناد احتياطي لحساب إدارة محدد.
"""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model


def get_primary_staff_user():
    """
    يعيد حساب الإدارة المعرّف في PRIMARY_ADMIN_USERNAME إن وُجد وكان staff نشطاً،
    وإلا أول مستخدم staff نشط.
    """
    User = get_user_model()
    username = getattr(settings, "PRIMARY_ADMIN_USERNAME", None) or ""
    username = username.strip()
    if username:
        u = User.objects.filter(username=username, is_staff=True, is_active=True).first()
        if u:
            return u
    return User.objects.filter(is_staff=True, is_active=True).order_by("id").first()
