"""
إشعارات بريد عند إنشاء سجلات عملاء أو تغيير التعيين (مسند إلى) في الأدمن.
"""

from __future__ import annotations

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import (
    FastRequest,
    PropertyBooking,
    PropertyLead,
    PropertyOffer,
    PropertyRequest,
    PropertySmartLink,
)
from .services.staff_email import collect_marketer_emails, notify_staff_action


def _marketer_emails_assigned(assigned_user):
    if assigned_user is None:
        return []
    return collect_marketer_emails(assigned_user)


def _marketer_emails_for_lead(instance: PropertyLead):
    users = []
    if instance.assigned_to_id:
        users.append(instance.assigned_to)
    if instance.smart_link_id:
        try:
            sl = PropertySmartLink.objects.select_related("marketer").get(
                pk=instance.smart_link_id
            )
            if sl.marketer_id:
                users.append(sl.marketer)
        except PropertySmartLink.DoesNotExist:
            pass
    return collect_marketer_emails(*users)


def _marketer_emails_for_fast(instance: FastRequest):
    if not instance.smart_link_id:
        return []
    try:
        sl = PropertySmartLink.objects.select_related("marketer").get(
            pk=instance.smart_link_id
        )
        if sl.marketer_id:
            return collect_marketer_emails(sl.marketer)
    except PropertySmartLink.DoesNotExist:
        pass
    return []


def _cache_prev_assigned(sender, instance, **kwargs):
    if not instance.pk:
        instance._prev_assigned_to_id = None
        return
    try:
        prev = sender.objects.only("assigned_to_id").get(pk=instance.pk)
        instance._prev_assigned_to_id = prev.assigned_to_id
    except sender.DoesNotExist:
        instance._prev_assigned_to_id = None


pre_save.connect(_cache_prev_assigned, sender=PropertyRequest)
pre_save.connect(_cache_prev_assigned, sender=PropertyOffer)
pre_save.connect(_cache_prev_assigned, sender=PropertyLead)
pre_save.connect(_cache_prev_assigned, sender=FastRequest)


@receiver(post_save, sender=PropertyRequest)
def email_on_property_request(sender, instance, created, **kwargs):
    if created:
        budget = instance.budget if instance.budget is not None else "—"
        notify_staff_action(
            f"طلب عقار جديد #{instance.pk}",
            (
                f"طلب بحث عن عقار جديد.\n"
                f"المعرف: #{instance.pk}\n"
                f"العميل: {instance.name}\n"
                f"الجوال: {instance.phone}\n"
                f"النوع: {instance.property_type}\n"
                f"الحي: {instance.district}\n"
                f"الميزانية: {budget}\n"
                f"المصدر: {getattr(instance, 'source', '')}\n"
            ),
            link_obj=instance,
            marketer_emails=_marketer_emails_assigned(
                instance.assigned_to if instance.assigned_to_id else None
            ),
        )
        return
    prev = getattr(instance, "_prev_assigned_to_id", None)
    if prev != instance.assigned_to_id:
        assignee = (
            instance.assigned_to.get_username()
            if instance.assigned_to_id
            else "غير معيّن"
        )
        notify_staff_action(
            f"تعيين طلب عقار #{instance.pk}",
            (
                f"تم تغيير «مسند إلى» لطلب العقار #{instance.pk}.\n"
                f"المسند إليه الآن: {assignee}\n"
                f"العميل: {instance.name} — {instance.phone}\n"
            ),
            link_obj=instance,
            marketer_emails=_marketer_emails_assigned(
                instance.assigned_to if instance.assigned_to_id else None
            ),
        )


@receiver(post_save, sender=PropertyOffer)
def email_on_property_offer(sender, instance, created, **kwargs):
    if created:
        notify_staff_action(
            f"عرض عقار جديد #{instance.pk}",
            (
                f"طلب تسويق / عرض عقار جديد من المالك.\n"
                f"المعرف: #{instance.pk}\n"
                f"المالك: {instance.owner_name or '—'}\n"
                f"الجوال: {instance.phone or '—'}\n"
                f"المدينة: {instance.city or '—'} — الحي: {instance.neighborhood or '—'}\n"
                f"النوع: {instance.property_type or '—'} — السعر: {instance.price or '—'}\n"
            ),
            link_obj=instance,
            marketer_emails=_marketer_emails_assigned(
                instance.assigned_to if instance.assigned_to_id else None
            ),
        )
        return
    prev = getattr(instance, "_prev_assigned_to_id", None)
    if prev != instance.assigned_to_id:
        assignee = (
            instance.assigned_to.get_username()
            if instance.assigned_to_id
            else "غير معيّن"
        )
        notify_staff_action(
            f"تعيين عرض عقار #{instance.pk}",
            (
                f"تم تغيير «مسند إلى» لعرض التسويق #{instance.pk}.\n"
                f"المسند إليه الآن: {assignee}\n"
                f"المالك: {instance.owner_name or '—'} — {instance.phone or '—'}\n"
            ),
            link_obj=instance,
            marketer_emails=_marketer_emails_assigned(
                instance.assigned_to if instance.assigned_to_id else None
            ),
        )


@receiver(post_save, sender=PropertyLead)
def email_on_property_lead(sender, instance, created, **kwargs):
    if created:
        prop_id = ""
        if instance.property_id:
            prop_id = getattr(instance.property, "listing_id", None) or str(
                instance.property_id
            )
        notify_staff_action(
            f"عميل محتمل / استفسار #{instance.pk}",
            (
                f"سجل عميل محتمل جديد (استفسار، بروشور، إلخ).\n"
                f"المعرف: #{instance.pk}\n"
                f"الاسم: {instance.name or '—'}\n"
                f"الجوال: {instance.phone or '—'}\n"
                f"العقار: {prop_id or '—'}\n"
                f"المصدر: {instance.source or '—'}\n"
                f"الرسالة: {(instance.message or '')[:500]}\n"
            ),
            link_obj=instance,
            marketer_emails=_marketer_emails_for_lead(instance),
        )
        return
    prev = getattr(instance, "_prev_assigned_to_id", None)
    if prev != instance.assigned_to_id:
        assignee = (
            instance.assigned_to.get_username()
            if instance.assigned_to_id
            else "غير معيّن"
        )
        notify_staff_action(
            f"تعيين عميل محتمل #{instance.pk}",
            (
                f"تم تغيير «مسند إلى» للعميل #{instance.pk}.\n"
                f"المسند إليه الآن: {assignee}\n"
                f"{instance.name or ''} — {instance.phone or ''}\n"
            ),
            link_obj=instance,
            marketer_emails=_marketer_emails_assigned(
                instance.assigned_to if instance.assigned_to_id else None
            ),
        )


@receiver(post_save, sender=FastRequest)
def email_on_fast_request(sender, instance, created, **kwargs):
    if created:
        notify_staff_action(
            f"طلب سريع #{instance.pk}",
            (
                f"طلب سريع من البطاقة الذكية.\n"
                f"المعرف: #{instance.pk}\n"
                f"الاسم: {instance.name}\n"
                f"الجوال: {instance.phone}\n"
                f"النص:\n{instance.request_text[:1500]}\n"
            ),
            link_obj=instance,
            marketer_emails=_marketer_emails_for_fast(instance),
        )
        return
    prev = getattr(instance, "_prev_assigned_to_id", None)
    if prev != instance.assigned_to_id:
        assignee = (
            instance.assigned_to.get_username()
            if instance.assigned_to_id
            else "غير معيّن"
        )
        notify_staff_action(
            f"تعيين طلب سريع #{instance.pk}",
            (
                f"تم تغيير «مسند إلى» للطلب السريع #{instance.pk}.\n"
                f"المسند إليه الآن: {assignee}\n"
                f"العميل: {instance.name} — {instance.phone}\n"
            ),
            link_obj=instance,
            marketer_emails=_marketer_emails_assigned(
                instance.assigned_to if instance.assigned_to_id else None
            ),
        )


@receiver(post_save, sender=PropertyBooking)
def email_on_property_booking(sender, instance, created, **kwargs):
    if not created:
        return
    lid = ""
    if instance.property_id:
        lid = getattr(instance.property, "listing_id", None) or str(instance.property_id)
    notify_staff_action(
        f"طلب حجز/معاينة #{instance.pk}",
        (
            f"طلب حجز أو معاينة جديد.\n"
            f"المعرف: #{instance.pk}\n"
            f"العميل: {instance.name}\n"
            f"الجوال: {instance.phone}\n"
            f"العقار: {lid}\n"
            f"التاريخ: {instance.booking_date} — الوقت: {instance.booking_time}\n"
            f"ملاحظات: {(instance.notes or '')[:500]}\n"
        ),
        link_obj=instance,
    )
