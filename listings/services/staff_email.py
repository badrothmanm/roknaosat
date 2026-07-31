"""
تنبيهات بريد للموظفين عند أحداث العملاء (طلب، عرض، استفسار، طلب سريع، تعيين، إلخ).
يُستدعى بعد commit المعاملة حتى لا يُرسل بريد لعمليات أُلغيت.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.urls import NoReverseMatch, reverse

logger = logging.getLogger(__name__)


def resolve_user_notify_email(user) -> str | None:
    """
    بريد استلام تنبيهات CRM للمسوّق: من الملف الشخصي إن وُجد، وإلا من حقل email في User.
    """
    if user is None:
        return None
    from listings.models import UserAccessProfile

    try:
        prof = UserAccessProfile.objects.only("notification_email").get(user_id=user.pk)
        addr = (prof.notification_email or "").strip()
        if addr:
            return addr
    except UserAccessProfile.DoesNotExist:
        pass
    addr = (getattr(user, "email", None) or "").strip()
    return addr or None


def collect_marketer_emails(*users) -> list[str]:
    """يجمع عناوين صالحة بدون تكرار."""
    seen: dict[str, None] = {}
    for u in users:
        e = resolve_user_notify_email(u)
        if e and "@" in e:
            seen.setdefault(e, None)
    return list(seen.keys())


def _absolute_admin_change_url(obj) -> str | None:
    try:
        path = reverse(
            f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change",
            args=[obj.pk],
        )
    except NoReverseMatch:
        return None
    base = (getattr(settings, "PUBLIC_SITE_URL", "") or "").rstrip("/")
    return f"{base}{path}" if base else path


def notify_staff_action(
    subject: str,
    body: str,
    *,
    link_obj=None,
    marketer_emails: list[str] | None = None,
) -> None:
    """
    يرسل بريداً إلى STAFF_ACTION_NOTIFY_EMAILS وأي عناوين إضافية للمسوّقين (بدون تكرار).
    إن وُجد link_obj يُضاف رابط تعديل السجل في الأدمن.
    """
    if not getattr(settings, "STAFF_EMAIL_NOTIFY_ENABLED", True):
        return
    base = list(getattr(settings, "STAFF_ACTION_NOTIFY_EMAILS", None) or [])
    extra = [e.strip() for e in (marketer_emails or []) if e and str(e).strip()]
    recipients = list(dict.fromkeys(base + extra))
    if not recipients:
        return

    text = body.rstrip()
    if link_obj is not None:
        url = _absolute_admin_change_url(link_obj)
        if url:
            text = f"{text}\n\nرابط في لوحة التحكم:\n{url}"

    def _send() -> None:
        try:
            send_mail(
                subject=f"[جودة CRM] {subject}",
                message=text,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipients,
                fail_silently=False,
            )
        except Exception as exc:
            logger.exception("فشل إرسال تنبيه البريد للموظفين: %s", exc)

    transaction.on_commit(_send)
