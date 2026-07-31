"""
listings/services/sheets_sync.py
=================================
Google Sheets sync for PropertyRequest.
Column order MUST match the sheet tab "طلب عقار" headers (right to left):

 A=التاريخ والوقت | B=اسم العميل | C=رقم الجوال | D=رابط واتساب
 E=نوع العقار | F=الحي | G=المدينة | H=سكني/تجاري (نوع الاستخدام)
 I=نوع الطلب | J=السعر (الميزانية) | K=عدد دورات المياه
 L=عدد الغرف | M=عدد الشقق | N=عدد الأدوار | O=المساحة
 P=عمر العقار | Q=وصف/ملاحظات إضافية

Tab "العقارات المعروضة" (A to Y):
A=رقم العقار | B=تاريخ النشر | C=اسم المالك | D=رقم الجوال
E=نوع العقار | F=نوع العرض | G=التصنيف | H=المدينة | I=الحي
J=المساحة | K=السعر | L=حالة السعر | M=رقم رخصة فال | N=رقم الإعلان
O=عمر العقار | P=الأدوار | Q=الغرف | R=الشقق | S=دورات المياه
T=الحالة الحالية | U=ملاحظات المالك | V=رابط الخريطة
W=رابط الفيديو | X=رابط البروشور | Y=عدد الاستفسارات
"""

import json
import logging
import threading

from django.conf import settings

logger = logging.getLogger(__name__)


def _parse_extra(notes_json: str) -> dict:
    """Parse JSON stored in PropertyRequest.notes, return empty dict on failure."""
    if not notes_json:
        return {}
    try:
        data = json.loads(notes_json)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _do_sync(request_id: int) -> None:
    """Runs in background thread. Fetches PropertyRequest and appends to Sheets."""
    try:
        from listings.models import PropertyRequest
        from integrations.sheets_client import SheetsClient
        from django.utils import timezone

        req = PropertyRequest.objects.get(pk=request_id)
        extra = _parse_extra(req.notes or "")

        dt_str = "'" + timezone.localtime(timezone.now()).strftime("%d/%m/%Y %H:%M:%S")
        wa_link = f"https://wa.me/{req.phone}"

        # ترتيب الأعمدة يطابق رؤوس الشيت تماماً بناءً على طلب العميل
        row = [
            dt_str,                                    # A - التاريخ والوقت
            req.name,                                  # B - اسم العميل
            req.phone,                                 # C - رقم الجوال
            wa_link,                                   # D - رابط واتساب
            req.property_type or "",                   # E - نوع العقار
            req.property_age or "",                    # F - عمر العقار
            req.area or "",                            # G - المساحة
            req.floors_count or "",                    # H - عدد الأدوار
            req.apartments_count or "",                # I - عدد الشقق
            req.rooms_count or "",                     # J - عدد الغرف
            req.bathrooms_count or "",                 # K - عدد دورات المياه
            str(req.budget or ""),                     # L - السعر
            req.request_type or "",                    # M - نوع الطلب (إيجار/ تملك)
            req.usage_type or "",                      # N - سكني / تجاري
            req.city or "جدة",                         # O - المدينة
            req.district or "",                        # P - الحي
            req.notes or "",                           # Q - حول وصف طلب العقار
        ]

        client = SheetsClient(
            spreadsheet_id=getattr(settings, "GSHEETS_SPREADSHEET_ID", None),
            service_account_file=getattr(
                settings, "GSHEETS_SERVICE_ACCOUNT_FILE", "core/keys/crm-sheets.json"
            ),
        )
        client.append_row(
            getattr(settings, "GSHEETS_REQUESTS_TAB", "طلب عقار"),
            row,
        )
        logger.info("[SheetsSync] PropertyRequest #%d synced successfully.", request_id)

    except Exception as exc:
        logger.error(
            "[SheetsSync] Failed to sync PropertyRequest #%d: %s",
            request_id, exc,
        )


def sync_property_request_async(request_id: int) -> None:
    """Public API: fire-and-forget background sync."""
    t = threading.Thread(target=_do_sync, args=(request_id,), daemon=True)
    t.start()


def _do_sync_property(property_id: int) -> None:
    """Sync Property model to Sheets "العقارات المعروضة"."""
    try:
        from listings.models import Property
        from integrations.sheets_client import SheetsClient
        from django.utils import timezone

        prop = Property.objects.get(pk=property_id)
        
        # رابط البروشور الكامل
        # نستخدم رابط الموقع الفعلي إذا كان متاحاً في الإعدادات
        base_domain = "https://jodah.sa"
        property_url = f"{base_domain}{prop.get_absolute_url()}"
        
        # تنسيق التاريخ
        published_dt = "'" + prop.created_at.astimezone(timezone.get_current_timezone()).strftime("%d/%m/%Y %H:%M")

        # رسم خريطة الأعمدة A-Y
        row = [
            prop.listing_id or "",             # A - رقم العقار
            published_dt,                       # B - تاريخ النشر
            prop.full_name or "",               # C - اسم المالك
            prop.phone or "",                   # D - رقم الجوال
            prop.property_type or "",           # E - نوع العقار
            prop.offer_type or "",              # F - نوع العرض
            prop.category or "",                # G - التصنيف
            prop.city or "جدة",                 # H - المدينة
            prop.district or "",                # I - الحي
            str(prop.area or ""),               # J - المساحة
            str(prop.price or ""),              # K - السعر
            prop.negotiation_status or "",      # L - حالة السعر
            prop.val_license or "",             # M - رقم رخصة فال
            prop.ad_number or "",               # N - رقم الإعلان
            prop.property_age or "",            # O - عمر العقار
            prop.floors or "",                  # P - عدد الأدوار
            prop.rooms or "",                   # Q - عدد الغرف
            prop.apartments or "",              # R - عدد الشقق
            prop.bathrooms or "",               # S - عدد دورات المياه
            prop.status or "",                  # T - الحالة الحالية
            prop.owner_notes or "",             # U - ملاحظات المالك
            prop.map_url or "",                  # V - رابط الخريطة
            prop.video_url or "",               # W - رابط الفيديو
            property_url,                       # X - رابط البروشور
            str(prop.inquiry_count or 0),       # Y - عدد الاستفسارات
        ]

        client = SheetsClient(
            spreadsheet_id=getattr(settings, "GSHEETS_SPREADSHEET_ID", None),
            service_account_file=getattr(
                settings, "GSHEETS_SERVICE_ACCOUNT_FILE", "core/keys/crm-sheets.json"
            ),
        )
        # ملاحظة: يجب أن يتطابق اسم التاب تماماً مع الموجود في قوقل شيت (بما في ذلك المسافات)
        tab_name = getattr(settings, "GSHEETS_PROPERTIES_TAB", "العقارات المعروضة ")
        client.append_row(tab_name, row)
        logger.info("[SheetsSync] Property #%d synced successfully.", property_id)

    except Exception as exc:
        logger.error("[SheetsSync] Failed to sync Property #%d: %s", property_id, exc)


def sync_published_property_async(property_id: int) -> None:
    """Fire-and-forget background sync for Property."""
    t = threading.Thread(target=_do_sync_property, args=(property_id,), daemon=True)
    t.start()


def _do_sync_offer(offer_id: int) -> None:
    """Sync PropertyOffer (leads from owners) to a specific Sheet tab."""
    try:
        from listings.models import PropertyOffer
        from integrations.sheets_client import SheetsClient
        from django.utils import timezone

        offer = PropertyOffer.objects.get(pk=offer_id)
        dt_str = "'" + timezone.localtime(timezone.now()).strftime("%d/%m/%Y %H:%M:%S")
        wa_link = f"https://wa.me/{offer.phone}"

        # We'll use a tab named "عروض الملاك" (Owner Offers) or similar
        row = [
            dt_str,                     # التاريخ
            offer.owner_name or "",     # اسم المالك
            offer.phone or "",           # رقم الجوال
            wa_link,                    # رابط واتساب
            offer.city or "",           # المدينة
            offer.neighborhood or "",   # الحي
            offer.property_type or "",  # نوع العقار
            offer.area or "",           # المساحة
            offer.price or "",          # السعر المطلوب
            offer.listing_type or "",   # نوع العرض (بيع/إيجار)
            offer.owner_notes or "",    # ملاحظات
        ]

        client = SheetsClient(
            spreadsheet_id=getattr(settings, "GSHEETS_SPREADSHEET_ID", None),
            service_account_file=getattr(
                settings, "GSHEETS_SERVICE_ACCOUNT_FILE", "core/keys/crm-sheets.json"
            ),
        )
        # Check if tab exists via client (or just try appending)
        tab_name = "طلبات تسويق الملاك"
        client.append_row(tab_name, row)
        logger.info("[SheetsSync] PropertyOffer #%d synced successfully.", offer_id)

    except Exception as exc:
        logger.error("[SheetsSync] Failed to sync PropertyOffer #%d: %s", offer_id, exc)


def sync_property_offer_async(offer_id: int) -> None:
    """Public API: fire-and-forget background sync for PropertyOffer."""
    t = threading.Thread(target=_do_sync_offer, args=(offer_id,), daemon=True)
    t.start()


def _do_sync_lead(lead_id: int) -> None:
    """Sync PropertyLead (interest from brochures/quick contact) to Sheets."""
    try:
        from listings.models import PropertyLead
        from integrations.sheets_client import SheetsClient
        from django.utils import timezone

        lead = PropertyLead.objects.get(pk=lead_id)
        # Use localized time if possible, or just strftime
        dt_str = "'" + lead.created_at.astimezone(timezone.get_current_timezone()).strftime("%d/%m/%Y %H:%M:%S")
        wa_link = f"https://wa.me/{lead.phone}"

        row = [
            dt_str,                                            # التاريخ
            lead.name or "",                                   # الاسم
            lead.phone or "",                                  # رقم الجوال
            wa_link,                                           # واتساب
            lead.property.listing_id if lead.property else "", # العقار المهتم به
            lead.source or "",                                 # المصدر
            lead.message or "",                                # الرسالة
        ]

        client = SheetsClient(
            spreadsheet_id=getattr(settings, "GSHEETS_SPREADSHEET_ID", None),
            service_account_file=getattr(
                settings, "GSHEETS_SERVICE_ACCOUNT_FILE", "core/keys/crm-sheets.json"
            ),
        )
        tab_name = "عملاء مهتمين (Brochures)"
        client.append_row(tab_name, row)
        logger.info("[SheetsSync] PropertyLead #%d synced successfully.", lead_id)
    except Exception as exc:
        logger.error("[SheetsSync] Failed to sync PropertyLead #%d: %s", lead_id, exc)


def sync_property_lead_async(lead_id: int) -> None:
    """Public API: fire-and-forget background sync for PropertyLead."""
    t = threading.Thread(target=_do_sync_lead, args=(lead_id,), daemon=True)
    t.start()
