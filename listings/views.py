import json
import re
import base64
import logging
import traceback
import random
import string
from io import BytesIO
from urllib.parse import quote
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import F
from django.http import HttpRequest, HttpResponse, JsonResponse, Http404
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required

from rest_framework import status, viewsets, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import Throttled
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .forms import AppointmentBookingForm
from .models import (
    Appointment,
    Property,
    PropertyLead,
    PropertyOffer,
    PropertyRequestImage,
    PropertySmartLink,
    FastRequest,
    PropertyBooking,
    CRMNotification,
    SmartLinkViewLog,
)
from .property_request_tasks import schedule_property_request_follow_up
from .services.property_request_lead import (
    compute_lead_score_and_priority,
    find_duplicate_property_request,
    mask_phone_for_log,
    sanitize_text_input,
)
from .throttles import PropertyRequestCreateThrottle
from .serializers import (
    PropertySerializer,
    FlatPropertySerializer,
    PropertyBookingSerializer,
    PropertyRequestCreateSerializer,
)
from .utils.api import api_success, api_error
from .services.ai_utils import generate_creative_description
from integrations.sheets_client import SheetsClient

logger = logging.getLogger(__name__)

WHATSAPP_PHONE = "966530460992"

# =========================
# Helpers
# =========================
def now_iso():
    return datetime.now(dt_timezone.utc).isoformat()

def safe_str(v):
    return "" if v is None else str(v)


_ARABIC_DIGIT_TRANSLATION = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789",
)


def _to_ascii_digits(value: str) -> str:
    """حوّل الأرقام العربية/الفارسية إلى إنجليزية قبل التحقق."""
    return (value or "").translate(_ARABIC_DIGIT_TRANSLATION)


def normalize_saudi_phone(phone: str) -> str:
    p = re.sub(r"\D", "", _to_ascii_digits(phone))
    if p.startswith("00"):
        p = p[2:]
    if p.startswith("0") and len(p) == 10 and p.startswith("05"):
        p = "966" + p[1:]
    elif len(p) == 9 and p.startswith("5"):
        p = "966" + p
    if p.startswith("966") and len(p) == 12:
        return p
    return p

def whatsapp_link(phone: str) -> str:
    p = normalize_saudi_phone(phone)
    return f"https://wa.me/{p}" if p else ""

def _get_client_ip(request: HttpRequest) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")

def _is_bot(user_agent: str) -> bool:
    """التحقق مما إذا كان الطلب قادم من محركات البحث أو برامج آلية."""
    if not user_agent:
        return False
    bots = [
        "googlebot", "bingbot", "yandexbot", "baiduspider", "slurp", 
        "duckduckbot", "ahrefsbot", "semrushbot", "dotbot", "rogerbot", 
        "exabot", "facebookexternalhit", "twitterbot", "linkedinbot"
    ]
    ua = user_agent.lower()
    return any(bot in ua for bot in bots)

def _absolute_url(request: HttpRequest, path: str) -> str:
    return request.build_absolute_uri(path)

# Images rules
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_MB = 10
MIN_IMAGES = 5
MAX_IMAGES = 10

# حدود طول المدخلات (حروف)
MAX_LEN_NAME = 200
MAX_LEN_PHONE = 20
MAX_LEN_MESSAGE = 2000
MAX_LEN_SUBJECT = 500
MAX_LEN_OWNER_NOTES = 2000

def _is_valid_image(f) -> bool:
    """التحقق من نوع الملف (MIME) وحجم الصورة."""
    if not f:
        return False
    content_type = (getattr(f, "content_type", "") or "").strip().lower()
    if content_type not in ALLOWED_MIME:
        return False
    if getattr(f, "size", 0) > MAX_IMAGE_MB * 1024 * 1024:
        return False
    return True


# =========================
# DRF ViewSet
# =========================
class PropertyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Property.objects.all()
    serializer_class = PropertySerializer

    def get_queryset(self):
        qs = Property.objects.filter(visibility="منشور").order_by("-created_at")

        offer_type = self.request.query_params.get("offer_type")
        property_type = self.request.query_params.get("property_type")
        district = self.request.query_params.get("district")
        max_price = self.request.query_params.get("max_price")

        if offer_type and offer_type != "all":
            qs = qs.filter(offer_type=offer_type)

        if property_type and property_type != "all":
            qs = qs.filter(property_type=property_type)

        if district:
            qs = qs.filter(district__icontains=district)

        if max_price:
            try:
                qs = qs.filter(price__lte=float(max_price))
            except ValueError:
                pass

        return qs


@staff_member_required
@require_POST
def generate_ai_copy(request):
    """
    API view to generate AI marketing text for a property.
    """
    try:
        data = json.loads(request.body)
        property_id = data.get('property_id')
        if not property_id:
            return JsonResponse({'success': False, 'error': 'Property ID missing'}, status=400)

        property_obj = get_object_or_404(Property, pk=property_id)
        success, content = generate_creative_description(property_obj)

        if success:
            return JsonResponse({'success': True, 'content': content})
        else:
            return JsonResponse({'success': False, 'error': content})

    except Exception as e:
        logger.error(f"AI Copy Exception: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


class N8NPropertyViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API ViewSet designed for n8n and AI consumption.
    Features:
    - Flat JSON structure
    - Filter by City and District
    - Search Filter in name and notes
    - Ordering by price and date
    """
    queryset = Property.objects.filter(visibility="منشور").order_by("-created_at")
    serializer_class = FlatPropertySerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    
    search_fields = ['full_name', 'owner_notes', 'district', 'city', 'property_type']
    ordering_fields = ['price', 'created_at', 'area']

    def get_queryset(self):
        qs = super().get_queryset()
        
        # Manual Filtering for City and District
        city = self.request.query_params.get("city")
        district = self.request.query_params.get("district")
        status = self.request.query_params.get("status")
        offer_type = self.request.query_params.get("offer_type")
        property_type = self.request.query_params.get("property_type")

        if city:
            qs = qs.filter(city__icontains=city)
        if district:
            qs = qs.filter(district__icontains=district)
        if status:
            qs = qs.filter(status=status)
        if offer_type:
            qs = qs.filter(offer_type=offer_type)
        if property_type:
            qs = qs.filter(property_type=property_type)

        return qs

    @action(detail=True, methods=["post"], url_path="track-inquiry")
    def track_inquiry(self, request, pk=None):
        try:
            prop = self.get_object()
            prop.inquiry_count += 1
            prop.save(update_fields=["inquiry_count"])
            return Response(
                {
                    "id": prop.id,
                    "listing_id": prop.listing_id,
                    "inquiry_count": prop.inquiry_count,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# =========================
# Pages
# =========================
def home(request):
    return render(request, "index.html")

def itmam_brochure(request):
    return render(request, "brochure.html")

def contact(request):
    return render(request, "contact.html")

def submit_property(request):
    context = {
        "crm_url": getattr(settings, "APPS_SCRIPT_URL", None),
        "crm_key": getattr(settings, "APPS_SCRIPT_KEY", None),
    }
    return render(request, "owner-offer.html", context)

def request_property(request):
    return render(request, "request-property.html")


def _build_cancel_url(request: HttpRequest, appointment: Appointment) -> str:
    path = reverse("listings:appointment-cancel", args=[appointment.cancel_token])
    return request.build_absolute_uri(path)


def _send_appointment_created_email(request: HttpRequest, appointment: Appointment) -> None:
    recipient = (appointment.client_email or "").strip()
    if not recipient:
        return
    cancel_url = _build_cancel_url(request, appointment)
    html_body = render_to_string(
        "emails/appointment_confirmation.html",
        {
            "appointment": appointment,
            "property": appointment.property,
            "cancel_url": cancel_url,
            "company_name": getattr(settings, "COMPANY_NAME", "جودة المستقبل"),
        },
    )
    text_body = (
        f"مرحباً {appointment.client_name}\n\n"
        f"تم تسجيل موعد المعاينة بنجاح.\n"
        f"العقار: {appointment.property.property_type} - {appointment.property.district}\n"
        f"التاريخ: {appointment.booking_date}\n"
        f"الوقت: {appointment.booking_time}\n\n"
        f"لإلغاء الموعد استخدم الرابط التالي:\n{cancel_url}\n"
    )
    mail = EmailMultiAlternatives(
        subject="تأكيد حجز موعد معاينة العقار",
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
    )
    mail.attach_alternative(html_body, "text/html")
    mail.send(fail_silently=False)


def _send_appointment_canceled_admin_email(request: HttpRequest, appointment: Appointment) -> None:
    recipients = list(getattr(settings, "STAFF_ACTION_NOTIFY_EMAILS", []) or [])
    if not recipients:
        return
    html_body = render_to_string(
        "emails/appointment_canceled_admin.html",
        {
            "appointment": appointment,
            "property": appointment.property,
            "admin_change_url": request.build_absolute_uri(
                reverse("admin:listings_appointment_change", args=[appointment.pk])
            ),
        },
    )
    text_body = (
        "تم إلغاء موعد معاينة.\n"
        f"العميل: {appointment.client_name}\n"
        f"الجوال: {appointment.client_phone}\n"
        f"البريد: {appointment.client_email or 'غير متوفر'}\n"
        f"العقار: {appointment.property.listing_id or appointment.property.pk}\n"
        f"التاريخ: {appointment.booking_date}\n"
        f"الوقت: {appointment.booking_time}\n"
    )
    mail = EmailMultiAlternatives(
        subject="تنبيه: تم إلغاء موعد معاينة",
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )
    mail.attach_alternative(html_body, "text/html")
    mail.send(fail_silently=False)


def _get_property_or_404(pk):
    """
    صفحة العقار العامة بالمعرّف الرقمي أو برقم العقار (listing_id) إذا طابق النص.
    تعرض أي سجل Property موجود (منشور أو مخفي) حتى تعمل الروابط المباشرة والمشاركة.
    قائمة العقارات في الموقع ما زالت تعرض «المنشور» فقط عبر /api/listings/.
    """
    prop = Property.objects.filter(pk=pk).first()
    if prop is None:
        prop = Property.objects.filter(listing_id=str(pk)).first()
    if prop is None:
        logger.warning("property_detail: no Property for pk=%s", pk)
        raise Http404(
            "لا يوجد عقار بهذا الرقم. تحقق من الرابط أو من أن البيانات متوفرة على هذا السيرفر."
        )
    return prop


def _render_property_detail(
    request: HttpRequest,
    prop: Property,
    *,
    appointment_form: AppointmentBookingForm | None = None,
    open_appointment_accordion: bool = False,
):
    form = appointment_form or AppointmentBookingForm()
    return render(
        request,
        "property-detail.html",
        {
            "property": prop,
            "appointment_form": form,
            "open_appointment_accordion": open_appointment_accordion,
        },
    )


def property_detail(request, pk):
    prop = _get_property_or_404(pk)
    return _render_property_detail(request, prop)


def property_detail_by_listing_id(request, listing_id):
    """فتح العقار برقم العقار المعروض (listing_id) بدل المفتاح الرقمي."""
    lid = (listing_id or "").strip()
    if not lid:
        raise Http404("رقم العقار غير صالح.")
    prop = Property.objects.filter(listing_id__iexact=lid).first()
    if prop is None:
        logger.warning("property_detail_by_listing_id: no Property for listing_id=%s", lid)
        raise Http404(
            "لا يوجد عقار بهذا الرقم التعريفي. تحقق من الرابط أو من صفحة الإدارة (رقم العقار)."
        )
    return _render_property_detail(request, prop)


@require_POST
def create_property_appointment(request, pk):
    """
    إنشاء موعد معاينة بدون تسجيل دخول.
    """
    prop = _get_property_or_404(pk)
    form = AppointmentBookingForm(request.POST or None)

    if not form.is_valid():
        messages.error(request, "تعذر حفظ الموعد. تحقق من البيانات المدخلة.")
        return _render_property_detail(
            request,
            prop,
            appointment_form=form,
            open_appointment_accordion=True,
        )

    booking_time_str = form.cleaned_data["booking_time"]
    booking_time_obj = datetime.strptime(booking_time_str, "%H:%M").time()
    booking_date = form.cleaned_data["booking_date"]

    conflict_exists = Appointment.objects.filter(
        property=prop,
        booking_date=booking_date,
        booking_time=booking_time_obj,
    ).exclude(status=Appointment.Status.CANCELED).exists()
    if conflict_exists:
        form.add_error("booking_time", "هذا الوقت محجوز مسبقاً، اختر فترة أخرى.")
        messages.warning(request, "الوقت المحدد غير متاح.")
        return _render_property_detail(
            request,
            prop,
            appointment_form=form,
            open_appointment_accordion=True,
        )

    appointment = form.save(commit=False)
    appointment.property = prop
    appointment.booking_time = booking_time_obj
    appointment.status = Appointment.Status.PENDING
    appointment.save()

    try:
        _send_appointment_created_email(request, appointment)
    except Exception:
        logger.exception("فشل إرسال بريد تأكيد الموعد id=%s", appointment.pk)

    if (appointment.client_email or "").strip():
        messages.success(request, "تم حجز موعدك بنجاح. أرسلنا تفاصيل الموعد إلى بريدك الإلكتروني.")
    else:
        messages.success(request, "تم حجز موعدك بنجاح.")
    return redirect(reverse("listings:property-detail", args=[prop.pk]) + "#appointment-booking")


def cancel_appointment(request, token):
    appointment = get_object_or_404(Appointment.objects.select_related("property"), cancel_token=token)
    already_canceled = appointment.status == Appointment.Status.CANCELED

    if not already_canceled:
        appointment.status = Appointment.Status.CANCELED
        appointment.save(update_fields=["status", "updated_at"])
        try:
            _send_appointment_canceled_admin_email(request, appointment)
        except Exception:
            logger.exception("فشل إرسال تنبيه إلغاء الموعد id=%s", appointment.pk)

    return render(
        request,
        "appointment_cancelled.html",
        {"appointment": appointment, "already_canceled": already_canceled},
    )

def privacy(request):
    return render(request, "privacy.html")

def terms(request):
    return render(request, "terms.html")


# =========================
# APIs
# =========================

def api_listings(request):
    """
    جلب العقارات من قاعدة بيانات Django للمتصفح
    تشمل حالة إظهار السعر للزوار
    """
    properties = Property.objects.filter(visibility='منشور').order_by('-created_at')

    # فلاتر البحث المتقدم
    offer_type = request.GET.get('offer_type')
    property_type = request.GET.get('property_type')
    district = request.GET.get('district')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')

    if offer_type and offer_type != 'all':
        # تعويض القيم إذا تم إرسالها بالإنجليزي
        if offer_type == 'sale': offer_type = 'بيع'
        if offer_type == 'rent': offer_type = 'إيجار'
        if offer_type == 'investment': offer_type = 'إستثمار'
        properties = properties.filter(offer_type=offer_type)
        
    if property_type and property_type != 'all':
        properties = properties.filter(property_type=property_type)
        
    if district:
        properties = properties.filter(district__icontains=district)
        
    if min_price:
        try:
            properties = properties.filter(price__gte=float(min_price))
        except ValueError:
            pass

    if max_price:
        try:
            properties = properties.filter(price__lte=float(max_price))
        except ValueError:
            pass

    data = []
    for prop in properties:
        data.append({
            "id": prop.id,
            "listing_id": prop.listing_id,
            "property_type": prop.property_type,
            "listing_type": prop.offer_type,
            "offer_type": prop.offer_type,
            "price": str(prop.price),
            "area": str(prop.area),
            "district": prop.district,
            "neighborhood": prop.district,
            "rooms": prop.rooms,
            "bathrooms": prop.bathrooms,
            "show_price": prop.show_price_to_visitors,
            "image_url": prop.image1.url if prop.image1 else "/static/img/hero_skyline.png",
            "display_price": prop.display_price if prop.display_price else None,
            "status": prop.status,
            "status_display": prop.get_status_display(),
        })
    return JsonResponse(data, safe=False)


def api_bulk_properties(request):
    """
    جلب مجموعة من العقارات بواسطة مصفوفة IDs (تستخدم للعقارات المشاهدة مؤخراً).
    """
    ids_raw = request.GET.get('ids', '')
    if not ids_raw:
        return JsonResponse([], safe=False)
    
    try:
        ids = [int(x) for x in ids_raw.split(',') if x.strip().isdigit()]
    except ValueError:
        return JsonResponse([], safe=False)
    
    properties = Property.objects.filter(id__in=ids, visibility='منشور')
    # الحفاظ على ترتيب الـ IDs المرسلة
    preserved = {p.id: p for p in properties}
    ordered_props = [preserved[id] for id in ids if id in preserved]

    data = []
    for prop in ordered_props:
        data.append({
            "id": prop.id,
            "listing_id": prop.listing_id,
            "property_type": prop.property_type,
            "price": str(prop.price),
            "display_price": prop.display_price,
            "area": str(prop.area),
            "district": prop.district,
            "image_url": prop.image1.url if prop.image1 else "/static/img/hero_skyline.png",
            "status": prop.status,
        })
    return JsonResponse(data, safe=False)


def api_similar_properties(request, pk):
    """
    جلب عقارات مشابهة للعقار الحالي (نفس النوع أو الحي).
    """
    prop = get_object_or_404(Property, pk=pk)
    
    base_qs = Property.objects.filter(visibility="منشور").exclude(pk=pk)
    # ترتيب زمني (أسرع بكثير من order_by('?')) مع أولوية لنفس النوع
    similar = list(base_qs.filter(property_type=prop.property_type).order_by("-created_at")[:3])
    if len(similar) < 3:
        seen_ids = [p.pk for p in similar]
        additional = list(
            base_qs.exclude(pk__in=seen_ids).order_by("-created_at")[: 3 - len(similar)]
        )
        similar.extend(additional)

    data = []
    for p in similar:
        data.append({
            "id": p.id,
            "listing_id": p.listing_id,
            "property_type": p.property_type,
            "price": str(p.price),
            "display_price": p.display_price,
            "area": str(p.area),
            "district": p.district,
            "image_url": p.image1.url if p.image1 else "/static/img/hero_skyline.png",
            "status": p.status,
        })
    return JsonResponse(data, safe=False)


@require_POST
@csrf_protect
def property_inquiry_api(request, pk: int):
    try:
        prop = get_object_or_404(Property, pk=pk)
        name = (request.POST.get("name") or "").strip()
        phone = (request.POST.get("phone") or "").strip()
        notes = (request.POST.get("notes") or "").strip()

        if not name or not phone:
            return api_error("الاسم والجوال مطلوبين", status=400)
        if len(name) > MAX_LEN_NAME:
            return api_error(f"الاسم يجب ألا يتجاوز {MAX_LEN_NAME} حرفاً.", status=400)
        if len(phone) > MAX_LEN_PHONE:
            return api_error(f"رقم الجوال يجب ألا يتجاوز {MAX_LEN_PHONE} حرفاً.", status=400)
        if len(notes) > MAX_LEN_MESSAGE:
            return api_error(f"الملاحظات يجب ألا تتجاوز {MAX_LEN_MESSAGE} حرفاً.", status=400)

        # Sheets (استفسار عقار)
        try:
            dt_str = timezone.localtime(timezone.now()).strftime("%d/%m/%Y %H:%M:%S")
            dt_cell = "'" + dt_str
            row = [
                safe_str(dt_cell), safe_str(name), safe_str(phone),
                safe_str(whatsapp_link(phone)), safe_str(notes), safe_str(prop.listing_id),
                safe_str(prop.offer_type), safe_str(prop.property_type), safe_str(prop.category),
                safe_str(prop.city), safe_str(prop.district), safe_str(prop.price),
                safe_str(prop.area), safe_str(prop.status), safe_str(prop.full_name),
                safe_str(prop.phone), safe_str(whatsapp_link(prop.phone)), safe_str(prop.owner_notes),
                safe_str(prop.inquiry_count + 1),
            ]
            client = SheetsClient(
                spreadsheet_id=getattr(settings, "GSHEETS_SPREADSHEET_ID", None),
                service_account_file=getattr(settings, "GSHEETS_SERVICE_ACCOUNT_FILE", "core/keys/crm-sheets.json"),
            )
            client.append_row(getattr(settings, "GSHEETS_INQUIRY_TAB", "استفسار عقار"), row)
        except Exception as sheet_err:
            logger.error(f"Sheet append failed for inquiry: {str(sheet_err)}")

        # DB Lead
        smart_link_id = request.POST.get("smart_link_id")
        smart_link_obj = None
        if smart_link_id:
            try:
                smart_link_obj = PropertySmartLink.objects.get(id=smart_link_id)
                PropertySmartLink.objects.filter(id=smart_link_id).update(inquiry_count=F("inquiry_count") + 1)
            except (PropertySmartLink.DoesNotExist, ValueError):
                pass

        lead = PropertyLead.objects.create(
            property=prop, name=name, phone=phone, message=notes,
            source="web", ip_address=_get_client_ip(request),
            smart_link=smart_link_obj
        )

        Property.objects.filter(pk=pk).update(inquiry_count=F("inquiry_count") + 1)

        wa_text = f"السلام عليكم، معك {name}. استفسار عن عقار رقم {prop.listing_id}. ملاحظات: {notes}"
        whatsapp_url = f"https://wa.me/{WHATSAPP_PHONE}?text={quote(wa_text)}"

        return api_success("تم استلام استفسارك بنجاح", data={"lead_id": lead.id, "whatsapp_url": whatsapp_url}, status=200)

    except Exception as e:
        logger.error(f"Error in property_inquiry_api: {str(e)}")
        return api_error("تعذر إرسال الاستفسار، حاول مرة أخرى.", status=500)


@require_POST
@csrf_protect
def general_contact_api(request):
    from .models import GeneralContact

    name = sanitize_text_input(
        (request.POST.get("name") or "").strip(),
        max_length=MAX_LEN_NAME,
    )
    phone = (request.POST.get("phone") or "").strip()
    subject = sanitize_text_input(
        (request.POST.get("subject") or "").strip(),
        max_length=MAX_LEN_SUBJECT,
    )

    if not name or not phone:
        return api_error("الاسم والجوال مطلوبين", status=400)
    if len(name) > MAX_LEN_NAME:
        return api_error(f"الاسم يجب ألا يتجاوز {MAX_LEN_NAME} حرفاً.", status=400)
    if len(phone) > MAX_LEN_PHONE:
        return api_error(f"رقم الجوال يجب ألا يتجاوز {MAX_LEN_PHONE} حرفاً.", status=400)
    if len(subject) > MAX_LEN_SUBJECT:
        return api_error(f"الموضوع يجب ألا يتجاوز {MAX_LEN_SUBJECT} حرفاً.", status=400)

    try:
        phone_norm = _validate_saudi_phone(phone)
    except ValueError as e:
        return api_error(str(e), status=400)

    try:
        contact = GeneralContact.objects.create(
            name=name,
            phone=phone_norm,
            subject=subject,
        )
    except Exception as e:
        logger.exception("general_contact_api DB save failed: %s", e)
        return api_error("حدث خطأ أثناء حفظ طلبك. حاول مرة أخرى.", status=500)

    # مزامنة اختيارية — لا تفشل الطلب إذا تعذّرت Sheets/البريد
    try:
        spreadsheet_id = getattr(settings, "GSHEETS_SPREADSHEET_ID", None)
        if spreadsheet_id:
            dt_str = timezone.localtime(timezone.now()).strftime("%d/%m/%Y %H:%M:%S")
            row = [
                "'" + dt_str,
                safe_str(name),
                safe_str(phone_norm),
                safe_str(whatsapp_link(phone_norm)),
                safe_str(subject),
            ]
            client = SheetsClient(
                spreadsheet_id=spreadsheet_id,
                service_account_file=getattr(
                    settings, "GSHEETS_SERVICE_ACCOUNT_FILE", "core/keys/crm-sheets.json"
                ),
            )
            client.append_row("تواصل عام", row)
    except Exception as e:
        logger.warning("general_contact_api sheets sync skipped: %s", e)

    try:
        from .services.staff_email import notify_staff_action

        notify_staff_action(
            "تواصل عام من الموقع",
            f"رسالة تواصل جديدة #{contact.id}\n"
            f"الاسم: {name}\n"
            f"الجوال: {phone_norm}\n"
            f"الموضوع: {subject}\n",
        )
    except Exception as e:
        logger.warning("general_contact_api email notify skipped: %s", e)

    return api_success(
        "تم استلام طلبك بنجاح",
        data={
            "id": contact.id,
            "name": name,
            "whatsapp_url": whatsapp_link(phone_norm),
        },
    )



import time
from collections import defaultdict

_rate_store: dict = defaultdict(list)
RATE_LIMIT_REQUESTS = 5
RATE_LIMIT_WINDOW = 60 * 10  # 10 minutes


def _check_rate_limit(ip: str) -> bool:
    now = time.time()
    _rate_store[ip] = [t for t in _rate_store[ip] if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_store[ip]) >= RATE_LIMIT_REQUESTS:
        return False
    _rate_store[ip].append(now)
    return True


def _validate_saudi_phone(phone: str) -> str:
    """Validates + normalizes Saudi phone → 9665XXXXXXXX or raises ValueError."""
    p = re.sub(r"[\s\-\(\)]+", "", _to_ascii_digits(phone or ""))
    p = re.sub(r"\D", "", p)
    if p.startswith("00"):
        p = p[2:]
    if p.startswith("0") and len(p) == 10 and p[1] == "5":
        p = "966" + p[1:]
    elif len(p) == 9 and p.startswith("5"):
        p = "966" + p
    elif p.startswith("9660") and len(p) == 13 and p[4] == "5":
        # 96605XXXXXXXX → 9665XXXXXXXX
        p = "966" + p[4:]
    if p.startswith("966") and len(p) == 12 and p[3] == "5":
        return p
    raise ValueError("رقم الجوال غير صحيح. اكتب رقم سعودي مثل: 05xxxxxxxx")


def _property_request_api_key_ok(request) -> bool:
    expected = (getattr(settings, "PROPERTY_REQUEST_API_KEY", None) or "").strip()
    if not expected:
        return True
    got = (request.headers.get("X-API-Key") or request.META.get("HTTP_X_API_KEY") or "").strip()
    return got == expected


def _process_property_request_create(request, payload) -> Response:
    """
    منطق إنشاء PropertyRequest من dict (مشترك بين الواجهة العامة ومسار n8n).
    """
    ip = _get_client_ip(request)
    logger.info(
        "property_request.api.incoming",
        extra={
            "event": "property_request_incoming",
            "path": request.path,
            "client_ip": ip,
            "content_type": request.content_type,
        },
    )

    if not _property_request_api_key_ok(request):
        logger.warning(
            "property_request.api.api_key_rejected",
            extra={"event": "api_key_rejected", "client_ip": ip},
        )
        return Response(
            {
                "success": False,
                "errors": {"detail": "Invalid or missing API key."},
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    serializer = PropertyRequestCreateSerializer(data=payload)
    if not serializer.is_valid():
        logger.warning(
            "property_request.api.validation_error",
            extra={
                "event": "property_request_validation_failed",
                "client_ip": ip,
                "errors": serializer.errors,
            },
        )
        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    vd = serializer.validated_data
    duplicate = find_duplicate_property_request(
        phone=vd["phone"],
        property_type=vd["property_type"],
        district=vd["district"],
        budget=vd["budget"],
    )
    if duplicate:
        logger.info(
            "property_request.api.duplicate",
            extra={
                "event": "property_request_duplicate",
                "client_ip": ip,
                "existing_request_id": duplicate.id,
                "phone_masked": mask_phone_for_log(vd["phone"]),
            },
        )
        return Response(
            {
                "success": True,
                "duplicate": True,
                "request_id": duplicate.id,
                "matched_count": duplicate.matched_count,
                "message": (
                    "A request with the same phone, property type, district, and budget "
                    "already exists."
                ),
            },
            status=status.HTTP_200_OK,
        )

    instance = serializer.save()
    rid = instance.id
    transaction.on_commit(lambda: schedule_property_request_follow_up(rid))
    logger.info(
        "property_request.api.created",
        extra={
            "event": "property_request_created",
            "request_id": rid,
            "client_ip": ip,
            "phone_masked": mask_phone_for_log(vd["phone"]),
            "source": vd.get("source"),
            "lead_score": instance.score,
            "priority": instance.priority,
        },
    )
    return Response(
        {
            "success": True,
            "request_id": instance.id,
            "message": "Request created successfully",
        },
        status=status.HTTP_201_CREATED,
    )


@method_decorator(csrf_exempt, name="dispatch")
class PropertyRequestCreateAPIView(APIView):
    """
    POST /api/property-requests/
    JSON body — unified pipeline (website, AI chat, WhatsApp integrations).

    Security: DRF AnonRateThrottle (scope property_request), optional X-API-Key if
    settings.PROPERTY_REQUEST_API_KEY is set.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    throttle_classes = [PropertyRequestCreateThrottle]

    def handle_exception(self, exc):
        if isinstance(exc, Throttled):
            return Response(
                {
                    "success": False,
                    "errors": {
                        "detail": "Too many requests. Please try again later.",
                    },
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        return super().handle_exception(exc)

    def post(self, request, *args, **kwargs):
        return _process_property_request_create(request, request.data)


class N8nPropertyRequestCreateAPIView(PropertyRequestCreateAPIView):
    """
    POST /api/n8n/property-request/ أو POST /n8n/property-request/

    يتحقق اختيارياً من Header: X-API-Key إذا وُجد PROPERTY_REQUEST_API_KEY في الإعدادات.
    يقبل JSON بما فيها name, phone, propertyType, district, budget (انظر normalize_n8n_property_request_payload).

    نفس التحقق والمفتاح الاختياري، مع تطبيع الحقول (camelCase، مرادفات) وافتراض
    source=ai_chat و category=family عند الحاجة — لتقليل أخطاء 400 من n8n.
    """

    def post(self, request, *args, **kwargs):
        from listings.utils.n8n_property_payload import normalize_n8n_property_request_payload

        raw = {}
        if hasattr(request.data, "items"):
            raw = dict(request.data)
        payload = normalize_n8n_property_request_payload(raw)
        return _process_property_request_create(request, payload)


# Keep old name as alias for backward-compat (frontend still calls this URL)
@csrf_exempt
@require_POST
def request_property_api(request):
    return property_request_api(request)


@csrf_exempt
@require_POST
def property_request_api(request):
    """
    API: استقبال طلب بحث عن عقار.
    1. Rate limit  2. Validate  3. Duplicate check
    4. DB save  5. Matching engine  6. Async Sheets sync  7. JSON response
    """
    from .models import PropertyRequest
    from decimal import Decimal

    ip = _get_client_ip(request)
    if not _check_rate_limit(ip):
        logger.warning("[PropertyRequest] Rate limit exceeded for IP %s", ip)
        return api_error("تم تجاوز الحد المسموح به من الطلبات. حاول لاحقاً.", status=429)

    # ── استخراج الحقول (تعقيم نصوص ضد تخزين HTML) ──
    name = sanitize_text_input(
        request.POST.get("name") or request.POST.get("client_name") or "",
        max_length=MAX_LEN_NAME,
    )
    phone_raw = (request.POST.get("phone") or "").strip()
    property_type = (request.POST.get("property_type") or "").strip()

    # أحياء متعددة من checkboxes أو نص مفصول
    districts_list = [
        (d or "").strip()
        for d in request.POST.getlist("districts")
        if (d or "").strip()
    ]
    if not districts_list:
        raw_district = (request.POST.get("district") or "").strip()
        if raw_district:
            districts_list = [
                p.strip()
                for p in re.split(r"[,،/\n]+", raw_district)
                if p.strip()
            ]
    district = "، ".join(districts_list)[:500] if districts_list else ""

    budget_raw = (
        request.POST.get("budget")
        or request.POST.get("price")
        or request.POST.get("budget_max")
        or ""
    ).strip()
    budget_range = (request.POST.get("budget_range") or "").strip()
    raw_source = (request.POST.get("source") or "website").strip().lower()
    valid_sources = {c[0] for c in PropertyRequest.SOURCE_CHOICES}
    source = raw_source if raw_source in valid_sources else "manual"

    # المواصفات الفنية (+ توافق أسماء المودال القديمة)
    request_type = (
        request.POST.get("request_type")
        or request.POST.get("offer_type")
        or ""
    ).strip()
    if request_type == "استثمار":
        request_type = "إستثمار"
    usage_type = (request.POST.get("usage_type") or "").strip()
    city = (request.POST.get("city") or "الرياض").strip() or "الرياض"
    area = (request.POST.get("area") or "").strip()
    property_age = (
        request.POST.get("property_age") or request.POST.get("age") or ""
    ).strip()
    floors_count = (
        request.POST.get("floors_count") or request.POST.get("floors") or ""
    ).strip()
    apartments_count = (
        request.POST.get("apartments_count") or request.POST.get("apartments") or ""
    ).strip()
    rooms_count = (
        request.POST.get("rooms_count") or request.POST.get("rooms") or ""
    ).strip()
    bathrooms_count = (
        request.POST.get("bathrooms_count") or request.POST.get("bathrooms") or ""
    ).strip()

    # توحيد أنواع العقار غير المدرجة في choices
    _type_aliases = {
        "دوبلكس": "فيلا",
        "مكتب": "محل تجاري",
        "معرض": "محل تجاري",
        "مستودع": "محل تجاري",
        "عمق": "عمارة",
    }
    property_type = _type_aliases.get(property_type, property_type)
    valid_property_types = {c[0] for c in Property.PROPERTY_TYPES}

    # ملاحظات العميل فقط (الوصف)
    notes = sanitize_text_input(
        request.POST.get("description") or "",
        max_length=MAX_LEN_MESSAGE,
    )

    errors = {}
    if not name:
        errors["name"] = "الاسم مطلوب."
    elif len(name) > MAX_LEN_NAME:
        errors["name"] = f"الاسم يجب ألا يتجاوز {MAX_LEN_NAME} حرفاً."
    if not property_type:
        errors["property_type"] = "نوع العقار مطلوب."
    elif property_type not in valid_property_types:
        errors["property_type"] = "نوع العقار غير صالح."
    if len(notes) > MAX_LEN_MESSAGE:
        errors["description"] = f"الملاحظات يجب ألا تتجاوز {MAX_LEN_MESSAGE} حرفاً."
    if not district:
        errors["district"] = "اختر حياً واحداً على الأقل."

    try:
        phone = _validate_saudi_phone(phone_raw)
    except ValueError as e:
        errors["phone"] = str(e)
        phone = phone_raw

    # الميزانية من نطاق جاهز أو قيمة رقمية
    budget = None
    budget_label = ""
    if budget_range:
        parts = budget_range.split("-", 1)
        if len(parts) == 2:
            lo, hi = parts[0].strip(), parts[1].strip()
            try:
                if hi == "plus":
                    budget = Decimal(lo.replace(",", ""))
                    budget_label = f"أكثر من {int(budget):,}"
                else:
                    lo_d = Decimal(lo.replace(",", "") or "0")
                    hi_d = Decimal(hi.replace(",", "") or "0")
                    budget = hi_d if hi_d > 0 else lo_d
                    budget_label = f"من {int(lo_d):,} إلى {int(hi_d):,}"
            except Exception:
                budget = None
    if budget is None and budget_raw:
        try:
            budget = Decimal(budget_raw.replace(",", ""))
            if budget <= 0:
                budget = None
        except Exception:
            budget = None

    if budget_label:
        prefix = f"الميزانية: {budget_label} ريال."
        notes = f"{prefix} {notes}".strip() if notes else prefix
        if len(notes) > MAX_LEN_MESSAGE:
            notes = notes[:MAX_LEN_MESSAGE]

    if errors:
        logger.warning(
            "property_request.legacy.validation_error",
            extra={"event": "legacy_validation_failed", "client_ip": ip, "errors": errors},
        )
        return JsonResponse({"success": False, "errors": errors}, status=400)

    # تكرار: نفس الجوال + نوع العقار + الحي + الميزانية (بما فيها الفارغة معاً)
    duplicate = find_duplicate_property_request(
        phone=phone,
        property_type=property_type,
        district=district,
        budget=budget,
    )
    if duplicate:
        logger.info(
            "property_request.legacy.duplicate",
            extra={
                "event": "legacy_duplicate",
                "client_ip": ip,
                "existing_request_id": duplicate.id,
                "phone_masked": mask_phone_for_log(phone),
            },
        )
        return JsonResponse({
            "success": True,
            "duplicate": True,
            "request_id": duplicate.id,
            "matched_count": duplicate.matched_count,
            "message": f"طلبك مسجل مسبقاً ووجدنا {duplicate.matched_count} عقار مطابق 🏠",
        })

    rooms_parsed = None
    if rooms_count:
        m = re.search(r"(\d+)", str(rooms_count))
        if m:
            try:
                rooms_parsed = int(m.group(1))
                if rooms_parsed > 50:
                    rooms_parsed = None
            except ValueError:
                rooms_parsed = None

    lead_score, lead_priority = compute_lead_score_and_priority(
        budget=budget,
        district=district,
        rooms=rooms_parsed,
        furnished=None,
        category=None,
        notes=notes or "",
        conversation_id=None,
        name=name,
    )

    try:
        req = PropertyRequest.objects.create(
            name=name, phone=phone, property_type=property_type,
            district=district, budget=budget, source=source,
            notes=notes, status="new",
            request_type=request_type or None, usage_type=usage_type or None,
            city=city, area=area, property_age=property_age,
            floors_count=floors_count, apartments_count=apartments_count,
            rooms_count=rooms_count, bathrooms_count=bathrooms_count,
            rooms=rooms_parsed,
            score=lead_score, priority=lead_priority,
        )
        logger.info(
            "property_request.legacy.created",
            extra={
                "event": "legacy_created",
                "request_id": req.id,
                "client_ip": ip,
                "phone_masked": mask_phone_for_log(phone),
                "lead_score": lead_score,
                "priority": lead_priority,
            },
        )
    except Exception as e:
        logger.exception("[PropertyRequest] DB save failed: %s", e)
        return api_error("حدث خطأ أثناء حفظ طلبك. حاول مرة أخرى.", status=500)

    # بعد commit حتى لا يتعارض خيط الخلفية مع معاملة SQLite أثناء الاختبارات
    rid = req.id
    transaction.on_commit(lambda: schedule_property_request_follow_up(rid))

    message = (
        "تم تسجيل طلبك ✅ سيتواصل معك أحد المسوقين قريباً. "
        "يتم البحث عن العقارات المطابقة في الخلفية."
    )
    return JsonResponse({"success": True, "matched_count": 0, "message": message, "request_id": req.id})




@require_POST
@csrf_protect
def api_offer_property(request):
    try:
        owner_name = (request.POST.get("owner_name") or "").strip()
        phone = (request.POST.get("phone") or "").strip()
        if not owner_name or not phone:
            return JsonResponse({"ok": False, "errors": {"phone": "البيانات ناقصة"}}, status=400)
        if len(owner_name) > MAX_LEN_NAME:
            return JsonResponse({"ok": False, "errors": {"owner_name": f"الاسم يجب ألا يتجاوز {MAX_LEN_NAME} حرفاً."}}, status=400)
        if len(phone) > MAX_LEN_PHONE:
            return JsonResponse({"ok": False, "errors": {"phone": f"رقم الجوال يجب ألا يتجاوز {MAX_LEN_PHONE} حرفاً."}}, status=400)

        owner_notes_raw = (request.POST.get("owner_notes") or "").strip()
        if len(owner_notes_raw) > MAX_LEN_OWNER_NOTES:
            return JsonResponse({"ok": False, "errors": {"owner_notes": f"الملاحظات يجب ألا تتجاوز {MAX_LEN_OWNER_NOTES} حرفاً."}}, status=400)

        images = request.FILES.getlist("images")
        if len(images) < MIN_IMAGES or len(images) > MAX_IMAGES:
            return JsonResponse({"ok": False, "errors": {"images": "العدد غير مسموح"}}, status=400)
        for i, f in enumerate(images):
            if not _is_valid_image(f):
                return JsonResponse({
                    "ok": False,
                    "errors": {
                        "images": f"الملف رقم {i + 1} غير صالح. يُقبل فقط صور (JPEG, PNG, WebP) بحجم أقصى {MAX_IMAGE_MB} ميجا."
                    },
                }, status=400)

        # 1. إنشاء الطلب في قاعدة البيانات بكامل الحقول المتاحة في الفورم
        offer = PropertyOffer.objects.create(
            owner_name=owner_name, 
            phone=phone, 
            whatsapp_url=whatsapp_link(phone),
            city=request.POST.get("city"), 
            neighborhood=request.POST.get("neighborhood"),
            property_type=request.POST.get("property_type"), 
            listing_type=request.POST.get("listing_type"),
            category=request.POST.get("category"), 
            area=request.POST.get("area"), 
            price=request.POST.get("price"),
            property_age=request.POST.get("property_age"),
            floors=request.POST.get("floors") or 0,
            apartments=request.POST.get("apartments") or 0,
            rooms=request.POST.get("rooms") or 0,
            bathrooms=request.POST.get("bathrooms") or 0,
            video_link=request.POST.get("video_link"),
            google_map=request.POST.get("google_map"),
            images_link=request.POST.get("images_link"),
            owner_notes=owner_notes_raw,
            status=PropertyOffer.Status.NEW,
        )

        for i, f in enumerate(images):
            PropertyRequestImage.objects.create(request=offer, image=f, is_cover=(i == 0), sort_order=i)

        # 2. إرسال البيانات إلى قوقل شيت في تبويب عرض عقار بالترتيب الصحيح
        try:
            dt_str = timezone.localtime(timezone.now()).strftime("%d/%m/%Y %H:%M:%S")
            row = [
                "'" + dt_str,                                     # A: التاريخ والوقت
                safe_str(owner_name),                             # B: اسم المالك
                safe_str(phone),                                  # C: رقم الجوال
                safe_str(whatsapp_link(phone)),                   # D: رابط واتساب
                safe_str(request.POST.get("property_type")),      # E: نوع العقار
                safe_str(request.POST.get("property_age")),       # F: عمر العقار
                safe_str(request.POST.get("area")),               # G: المساحة
                safe_str(request.POST.get("floors")),             # H: عدد الأدوار
                safe_str(request.POST.get("apartments")),         # I: عدد الشقق
                safe_str(request.POST.get("rooms")),              # J: عدد الغرف
                safe_str(request.POST.get("bathrooms")),          # K: دورات المياه
                safe_str(request.POST.get("price")),              # L: السعر
                safe_str(request.POST.get("neighborhood")),       # M: الحي
                safe_str(request.POST.get("listing_type")),       # N: نوع العرض
                safe_str(request.POST.get("category")),           # O: سكني / تجاري
                safe_str(request.POST.get("city")),               # P: المدينة
                "",                                               # Q: عمود فارغ (أو استخدمه لحقل آخر كان موجوداً هنا)
                safe_str(request.POST.get("google_map")),         # R: رابط قوقل ماب
                safe_str(owner_notes_raw),                        # S: وصف العقار
                safe_str(request.POST.get("video_link")),         # T: رابط فيديو
            ]
            client = SheetsClient(
                spreadsheet_id=getattr(settings, "GSHEETS_SPREADSHEET_ID", None),
                service_account_file=getattr(settings, "GSHEETS_SERVICE_ACCOUNT_FILE", "core/keys/crm-sheets.json")
            )
            client.append_row("عرض عقار", row)
        except Exception as sheet_err:
            logger.error(f"Sheet append failed for property offer: {str(sheet_err)}")

        return JsonResponse({"ok": True, "id": offer.id})
    except Exception as e:
        logger.error(f"Critical error: {str(e)}")
        return JsonResponse({"status": "error"}, status=500)


def property_qr_card(request: HttpRequest, pk: int) -> HttpResponse:
    prop = get_object_or_404(Property, pk=pk)
    details_path = reverse("listings:property-detail", args=[prop.pk])
    target_url = _absolute_url(request, details_path)
    
    import qrcode
    qr = qrcode.QRCode(box_size=10, border=1)
    qr.add_data(target_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    # Linguistic improvements for Arabic titles (Definite articles + Gender agreement)
    prop_type_raw = (prop.property_type or "").strip()
    offer_raw = (prop.offer_type or "").strip()
    category_raw = (prop.category or "").strip()

    # 1. Standardize Property Type with definite article
    type_mapping = {
        'شقة': 'الشقة',
        'فيلا': 'الفيلا',
        'قصر': 'القصر',
        'أرض': 'الأرض',
        'استراحة': 'الاستراحة',
        'محل': 'المحل',
        'مكتب': 'المكتب',
        'دور': 'الدور',
        'عمارة': 'العمارة',
    }
    prop_type = type_mapping.get(prop_type_raw, f"ال{prop_type_raw}" if prop_type_raw and not prop_type_raw.startswith('ال') else prop_type_raw)

    # 2. Handle Offer Type with proper prefix and hamzas
    if offer_raw == 'بيع':
        offer_phrase = 'للبيع'
    elif offer_raw in ['إيجار', 'ايجار']:
        offer_phrase = 'للإيجار'
    elif offer_raw == 'استثمار':
        offer_phrase = 'للاستثمار'
    else:
        offer_phrase = f"لل{offer_raw}" if offer_raw and not offer_raw.startswith('لل') else offer_raw

    display_title = f"{prop_type}\n{offer_phrase}"

    return render(request, "listings/property_qr_card.html", {
        "property": prop,
        "target_url": target_url,
        "qr_png_base64": qr_b64,
        "display_title": display_title,
        "val_license": request.GET.get('val', ''),
        "ad_number": request.GET.get('ad', ''),
    })


@require_POST
def generate_smart_link(request, pk: int):
    """
    توليد الرابط الذكي لمشاركة العرض.
    """
    prop = get_object_or_404(Property, pk=pk)
    # Check if a link already exists, if not create one
    smart_link, created = PropertySmartLink.objects.get_or_create(property=prop)
    
    # Generate the absolute url based on token
    base_url = f"{request.scheme}://{request.get_host()}"
    link_url = f"{base_url}/s/{smart_link.token}/"
    
    return JsonResponse({"ok": True, "smart_link": link_url})


def smart_brochure_view(request, token: str):
    """
    صفحة عرض البروشور الذكي. يزيد عداد المشاهدات الحقيقية والفريدة.
    """
    smart_link = get_object_or_404(PropertySmartLink, token=token)
    
    ip = _get_client_ip(request)
    ua = request.META.get("HTTP_USER_AGENT", "")
    
    # التحقق من الأداء الحقيقي: استبعاد الروبوتات وفحوصات الـ IP المتكررة في آخر 24 ساعة
    if not _is_bot(ua):
        since = timezone.now() - timedelta(hours=24)
        exists = SmartLinkViewLog.objects.filter(
            smart_link=smart_link,
            ip_address=ip,
            created_at__gte=since
        ).exists()
        
        if not exists:
            # تسجيل المشاهدة
            SmartLinkViewLog.objects.create(
                smart_link=smart_link,
                ip_address=ip,
                user_agent=ua
            )
            # تحديث عداد المشاهدات في الرابط الذكي بشكل آمن
            PropertySmartLink.objects.filter(pk=smart_link.pk).update(views=F('views') + 1)
            # تحديث عداد العقار العام أيضاً لو أردت (اختياري)
            # Property.objects.filter(pk=smart_link.property.pk).update(views=F('views') + 1)

    return render(request, "listings/brochure.html", {
        "property": smart_link.property, 
        "smart_link": smart_link,
        "marketer": smart_link.marketer
    })

def smart_site_card_view(request):
    """
    يعرض البطاقة الذكية الشاملة للموقع (نمط Linktree).
    """
    context = {
        'company_name': getattr(settings, 'COMPANY_NAME', 'جودة المستقبل'),
        'company_name_full': getattr(settings, 'COMPANY_NAME_FULL', 'جودة المستقبل للتطوير والاستثمار العقاري'),
        'company_whatsapp': getattr(settings, 'COMPANY_WHATSAPP', ''),
        'company_instagram': getattr(settings, 'COMPANY_INSTAGRAM', ''),
        'company_phone': getattr(settings, 'COMPANY_PHONE', ''),
    }
    return render(request, "smart_site_card.html", context)

@staff_member_required
@csrf_protect
def marketer_dashboard_view(request):
    """
    View for the Marketer Analytics Dashboard.
    Only accessible to staff or specific marketers.
    """
    if not request.user.is_authenticated:
        from django.shortcuts import redirect
        return redirect('admin:login')
        
    from django.contrib.auth.models import User
    from listings.utils.staff_permissions import staff_is_co_admin
    can_view_team_analytics = bool(request.user.is_superuser or staff_is_co_admin(request.user))
    is_co_admin = staff_is_co_admin(request.user)
    
    # Permission check: Only admin can view others
    target_user_id = request.GET.get('user_id')
    team_scope = False
    if target_user_id and can_view_team_analytics:
        try:
            selected_user_id = int(target_user_id)
        except (TypeError, ValueError):
            selected_user_id = request.user.id
    elif is_co_admin:
        # المدير المشارك يبدأ افتراضياً على «ملخص الفريق» ما لم يختَر مسوّقاً محدداً.
        selected_user_id = None
        team_scope = True
    else:
        selected_user_id = request.user.id
        
    from listings.services.dashboard_service import DashboardService
    period = request.GET.get('period', 'all')
    team_overview = None
    if can_view_team_analytics:
        team_overview = DashboardService.get_marketers_overview(period=period)

    if team_scope and team_overview:
        team_stats = team_overview.get("team_stats", {})
        marketers_rows = team_overview.get("marketers", []) or []
        assigned_tasks_total = sum((r.get("tasks", {}) or {}).get("total", 0) for r in marketers_rows)
        stats = {
            "total_links": team_stats.get("total_links", 0),
            "total_views": team_stats.get("total_views", 0),
            "total_leads": team_stats.get("total_leads", 0),
            "conversion_rate": team_stats.get("avg_conv_rate", "0.0%"),
            "assigned_tasks": [],
            "assigned_tasks_total": assigned_tasks_total,
            "available_properties": [],
            "general_link": "",
            "period": period,
            "has_any_brochure": bool(team_stats.get("total_links", 0)),
        }
    else:
        target_stats_user_id = selected_user_id or request.user.id
        stats = DashboardService.get_marketer_stats(target_stats_user_id, period=period)
        stats["has_any_brochure"] = any(
            p.get("has_link") for p in stats.get("available_properties") or []
        )
    
    # قائمة المسوّقين للمدير: ترتيب badr9090 (PRIMARY_ADMIN) ثم b1 (PRIMARY_MARKETER) ثم البقية
    marketers = []
    if can_view_team_analytics:
        from listings.utils.marketer_ordering import annotate_staff_marketer_sort

        mq = User.objects.filter(is_staff=True).only("id", "username", "first_name", "last_name")
        marketers = annotate_staff_marketer_sort(mq, settings)
        selected_user = User.objects.filter(id=selected_user_id, is_staff=True).first() if selected_user_id else request.user
        selected_user = selected_user or request.user
    else:
        selected_user = request.user

    # --- ميزات المرحلة 8: نظام CRM الذكي ---
    from listings.models import CRMNotification
    from django.urls import reverse
    from urllib.parse import urlencode

    # جلب التنبيهات غير المقروءة للمنتصفح الحالي
    unread_notifications = CRMNotification.objects.filter(
        user=request.user, 
        is_read=False
    )[:10]

    # روابط إدارة سريعة (لوحة المسوّق)
    admin_urls = {
        "users": reverse("admin:auth_user_changelist"),
        "user_add": reverse("admin:auth_user_add"),
        "groups": reverse("admin:auth_group_changelist"),
        "property_requests": reverse("admin:listings_propertyrequest_changelist"),
        "property_leads": reverse("admin:listings_propertylead_changelist"),
        "smart_links": reverse("admin:listings_propertysmartlink_changelist"),
        "smart_link_add": reverse("admin:listings_propertysmartlink_add"),
        "properties": reverse("admin:listings_property_changelist"),
    }
    pr_changelist = reverse("admin:listings_propertyrequest_changelist")
    link_filter_user_id = selected_user_id or request.user.id
    admin_urls["requests_assigned_to_marketer"] = (
        f"{pr_changelist}?{urlencode({'assigned_to__id__exact': link_filter_user_id})}"
    )
    po_changelist = reverse("admin:listings_propertyoffer_changelist")
    admin_urls["offers_assigned_to_marketer"] = (
        f"{po_changelist}?{urlencode({'assigned_to__id__exact': link_filter_user_id})}"
    )

    period_presets = []
    for key, label in (
        ("today", "اليوم"),
        ("7days", "آخر 7 أيام"),
        ("30days", "آخر 30 يوماً"),
        ("6months", "6 أشهر"),
        ("all", "كل الفترات"),
    ):
        q = {"period": key}
        if can_view_team_analytics and selected_user_id:
            q["user_id"] = str(selected_user_id)
        period_presets.append({"key": key, "label": label, "query": urlencode(q)})

    # إن وُجد staff بدون صلاحيات نماذج listings، روابط /admin/listings/... تعيد 403
    missing_marketer_admin_perms = []
    if not can_view_team_analytics:
        def _has_any(*codes):
            return any(request.user.has_perm(c) for c in codes)

        if not _has_any("listings.view_propertylead", "listings.change_propertylead"):
            missing_marketer_admin_perms.append("العملاء المحتملون")
        if not _has_any("listings.view_propertyrequest", "listings.change_propertyrequest"):
            missing_marketer_admin_perms.append("طلبات العقار / طلباتي المسندة")
        if not _has_any("listings.view_propertyoffer", "listings.change_propertyoffer"):
            missing_marketer_admin_perms.append("طلبات تسويق العقارات المسندة")
        if not _has_any(
            "listings.view_propertysmartlink",
            "listings.change_propertysmartlink",
            "listings.add_propertysmartlink",
        ):
            missing_marketer_admin_perms.append("الروابط الذكية")

    return render(request, "admin/marketer_dashboard.html", {
        "custom_js": "js/admin_custom.js?v=17",
        "stats": stats,
        "team_overview": team_overview,
        "period": period,
        "marketers": marketers,
        "selected_user_adj": selected_user,
        "selected_user_id": selected_user_id,
        "team_scope": team_scope,
        "unread_notifications": unread_notifications,
        "admin_urls": admin_urls,
        "period_presets": period_presets,
        "missing_marketer_admin_perms": missing_marketer_admin_perms,
        "primary_admin_username": getattr(settings, "PRIMARY_ADMIN_USERNAME", "") or "",
        "primary_marketer_username": getattr(settings, "PRIMARY_MARKETER_USERNAME", "") or "",
        "can_view_team_analytics": can_view_team_analytics,
        "title": (
            f"إحصائياتي — عرض كـ {request.user.get_full_name() or request.user.username}"
            if getattr(request, "impersonator", None)
            else (
                "إحصائيات المسوقين — ملخص الفريق"
                if can_view_team_analytics and team_scope
                else ("إحصائيات المسوقين" if can_view_team_analytics else "إحصائياتي")
            )
        ),
    })


def get_superuser_actor(request):
    """المستخدم الذي يملك صلاحية التبديل: المدير الحقيقي أثناء التمثيل أو المستخدم الحالي."""
    return getattr(request, "impersonator", None) or request.user


@staff_member_required
@require_POST
@csrf_protect
def impersonate_start_view(request):
    """
    يبدأ جلسة «الدخول كمسوّق» للمدير دون تسجيل خروج (superuser فقط).
    """
    actor = get_superuser_actor(request)
    if not actor.is_superuser:
        messages.error(request, "التبديل متاح لمدير النظام فقط.")
        return redirect("admin:index")
    raw = request.POST.get("user_id")
    try:
        user_id = int(raw)
    except (TypeError, ValueError):
        messages.error(request, "معرف المستخدم غير صالح.")
        return redirect("listings:marketer-dashboard")
    from django.contrib.auth import get_user_model

    User = get_user_model()
    target = get_object_or_404(User, pk=user_id, is_active=True)
    if not target.is_staff:
        messages.error(request, "يمكن التبديل إلى حسابات موظفين (staff) فقط.")
        return redirect("listings:marketer-dashboard")
    if target.is_superuser and target.pk != actor.pk:
        messages.error(request, "لا يمكن التبديل إلى حساب مدير آخر.")
        return redirect("listings:marketer-dashboard")
    request.session["impersonate_user_id"] = target.pk
    request.session["_impersonator_id"] = actor.pk
    label = target.get_full_name() or target.username
    messages.success(
        request,
        f"أنت الآن تعمل بحساب «{label}». استخدم الشريط العلوي للعودة إلى حساب المدير دون تسجيل خروج.",
    )
    return redirect("listings:marketer-dashboard")


@staff_member_required
@require_POST
@csrf_protect
def impersonate_stop_view(request):
    """إنهاء التبديل والعودة لحساب المدير."""
    if not request.session.get("impersonate_user_id"):
        return redirect("admin:index")
    request.session.pop("impersonate_user_id", None)
    request.session.pop("_impersonator_id", None)
    messages.success(request, "عدت إلى حساب المدير.")
    return redirect("admin:index")


@require_POST
def api_submit_fast_request(request):
    """
    API لاستقبال الطلب السريع من البطاقة الذكية دون تحديث الصفحة.
    """
    try:
        data = json.loads(request.body)
        name = data.get("name")
        phone = data.get("phone")
        request_text = data.get("request_text")

        if not all([name, phone, request_text]):
            return JsonResponse({"ok": False, "error": "Missing fields"}, status=400)
        name = (name or "").strip()
        phone = (phone or "").strip()
        request_text = (request_text or "").strip()
        smart_link_id = data.get("smart_link_id")

        if len(name) > MAX_LEN_NAME:
            return JsonResponse({"ok": False, "error": f"الاسم يجب ألا يتجاوز {MAX_LEN_NAME} حرفاً."}, status=400)
        if len(phone) > MAX_LEN_PHONE:
            return JsonResponse({"ok": False, "error": f"رقم الجوال يجب ألا يتجاوز {MAX_LEN_PHONE} حرفاً."}, status=400)
        if len(request_text) > MAX_LEN_MESSAGE:
            return JsonResponse({"ok": False, "error": f"نص الطلب يجب ألا يتجاوز {MAX_LEN_MESSAGE} حرفاً."}, status=400)

        smart_link_obj = None
        if smart_link_id:
            try:
                smart_link_obj = PropertySmartLink.objects.get(id=smart_link_id)
                # زيادة عداد الرابط الذكي
                PropertySmartLink.objects.filter(id=smart_link_id).update(inquiry_count=F("inquiry_count") + 1)
                # زيادة عداد العقار نفسه كونه استفسار
                if smart_link_obj.property:
                    Property.objects.filter(pk=smart_link_obj.property.pk).update(inquiry_count=F("inquiry_count") + 1)
            except PropertySmartLink.DoesNotExist:
                pass

        fast_req = FastRequest.objects.create(
            name=name,
            phone=phone,
            request_text=request_text,
            smart_link=smart_link_obj,
        )

        # 🔔 تنبيه للمسوق أو المدير
        try:
            target_user = None
            if smart_link_obj and smart_link_obj.marketer:
                target_user = smart_link_obj.marketer
            else:
                from django.contrib.auth.models import User
                target_user = User.objects.filter(is_superuser=True).first()

            if target_user:
                CRMNotification.objects.create(
                    user=target_user,
                    title="استفسار سريع جديد ⚡",
                    message=f"وصل استفسار جديد من {name} ({phone}) بخصوص العقار {smart_link_obj.property.listing_id if smart_link_obj and smart_link_obj.property else 'غير محدد'}.\nنص الطلب: {request_text}",
                    link=reverse("admin:listings_fastrequest_changelist"),
                )
        except Exception as notify_err:
            logger.error(f"Failed to create CRMNotification for FastRequest: {notify_err}")

        # 📊 مزامنة مع قوقل شيت (طلبات سريعة)
        try:
            dt_str = timezone.localtime(timezone.now()).strftime("%d/%m/%Y %H:%M:%S")
            row = [
                "'" + dt_str,
                name,
                phone,
                f"https://wa.me/{normalize_saudi_phone(phone)}",
                request_text,
                smart_link_obj.property.listing_id if smart_link_obj and smart_link_obj.property else "Direct/Site",
                smart_link_obj.marketer.username if smart_link_obj and smart_link_obj.marketer else "عام",
                "رابط ذكي" if smart_link_obj else "بطاقة موقع",
            ]
            client = SheetsClient(
                spreadsheet_id=getattr(settings, "GSHEETS_SPREADSHEET_ID", None),
                service_account_file=getattr(settings, "GSHEETS_SERVICE_ACCOUNT_FILE", "core/keys/crm-sheets.json"),
            )
            client.append_row("استفسار سريع", row)
        except Exception as sheet_err:
            logger.error(f"Sheet sync failed for FastRequest: {sheet_err}")

        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@staff_member_required
def admin_stats_api(request):
    """
    API خاص بالداش بورد: يُعيد أرقام KPI وآخر الطلبات والعروض والتحليلات.
    يتطلب أن يكون المستخدم staff.
    """
    from .services.dashboard_service import DashboardService
    period = request.GET.get("period", "all")
    
    try:
        data = DashboardService.get_dashboard_data(period)
        return JsonResponse(data)
    except Exception as e:
        logger.error(f"[AdminStatsAPI] Error fetching dashboard data: {e}")
        return JsonResponse({"error": "Failed to fetch dashboard data"}, status=500)

@staff_member_required
def api_get_marketers(request):
    """
    API returns a list of active staff members (marketers).
    """
    from django.contrib.auth.models import User
    # Only staff members who are not superusers (or all staff if requested)
    marketers = User.objects.filter(is_staff=True).values('id', 'first_name', 'last_name', 'username')
    return JsonResponse({"marketers": list(marketers)})


@api_view(['POST'])
@permission_classes([AllowAny])
def create_booking_api(request):
    """
    API: استقبال طلب حجز أو معاينة من n8n/AI.
    """
    serializer = PropertyBookingSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response({
            "ok": True, 
            "message": "تم تسجيل طلب المعاينة بنجاح.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)
    
    return Response({
        "ok": False, 
        "errors": serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)
@staff_member_required
@require_POST
def api_activate_marketer_link(request):
    """
    API لتفعيل رابط ذكي لمسوق على عقار معين.
    """
    try:
        import json
        data = json.loads(request.body)
        property_id = data.get("property_id")
        
        if not property_id:
            return JsonResponse({"error": "Property ID is required"}, status=400)
            
        from listings.models import Property, PropertySmartLink
        
        # التأكد من وجود العقار
        prop = Property.objects.filter(id=property_id).first()
        if prop is None:
            return JsonResponse({"error": "Property not found"}, status=404)
        
        # إنشاء أو استرجاع الرابط
        link, created = PropertySmartLink.objects.get_or_create(
            property=prop,
            marketer=request.user
        )
        
        return JsonResponse({
            "status": "success",
            "created": created,
            "token": link.token
        })
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)
    except Exception as e:
        logger.exception("api_activate_marketer_link failed: %s", e)
        return JsonResponse({"error": "Internal server error"}, status=500)


@staff_member_required
def owner_performance_view(request, pk):
    """
    Dashboard for property owners to see how their listing is performing.
    Includes views (from smart links), inquiries (leads), and matches.
    """
    from .models import Property, PropertyLead, PropertyMatch, PropertySmartLink
    
    prop = get_object_or_404(Property, pk=pk)
    
    # Calculate stats
    total_leads = prop.leads.count()
    total_matches = prop.request_matches.count()
    
    # Get smart link views
    smart_links = prop.smart_links.all()
    total_views = sum(link.views for link in smart_links)
    
    # Recent leads
    recent_leads = prop.leads.order_by('-created_at')[:8]
    
    # High-intent matches (leads looking for this exact type/district)
    high_matches = prop.request_matches.filter(score__gte=0.7).order_by('-score')[:10]
    
    context = {
        'property': prop,
        'total_leads': total_leads,
        'total_matches': total_matches,
        'total_views': total_views,
        'recent_leads': recent_leads,
        'high_matches': high_matches,
        'smart_links': smart_links,
    }
    
    return render(request, 'admin/owner_performance.html', context)
