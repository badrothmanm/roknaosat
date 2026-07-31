from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils.decorators import method_decorator
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.http import HttpResponse
from django.views.decorators.debug import sensitive_post_parameters
import re
from decimal import Decimal, InvalidOperation
from .models import (
    Property, PropertyOffer, PropertyLead, PropertyRequestImage, PropertySmartLink,
    FastRequest, PropertyRequest, PropertyMatch, UserAccessProfile, PropertyBooking, Appointment,
    CRMNotification, SmartLinkViewLog, SiteTicker, SiteAdBanner, GeneralContact,
)
from .services.sheets_sync import (
    sync_published_property_async,
    sync_property_lead_async,
)
from apps.publishing.services.publisher_service import PublisherService, PublishRequest
from django.contrib.auth.models import User, Group, Permission
from django.contrib.auth.admin import UserAdmin, GroupAdmin

from .permission_labels import ReadablePermissionMultipleChoiceField
from .forms_admin import JodahAdminUserCreationForm, JodahUserChangeForm
from .utils.staff_permissions import (
    admin_actor,
    staff_is_co_admin,
    staff_may_access_users_groups,
    staff_may_add_users,
    staff_may_change_passwords,
)

# -----------------------------------------------------
# إدارة المستخدمين (User Admin)
# -----------------------------------------------------
class UserAccessProfileInline(admin.StackedInline):
    model = UserAccessProfile
    can_delete = False
    verbose_name = "تحديد صلاحية الدخول"
    verbose_name_plural = "تحديد صلاحية الدخول"
    fields = ("access_start_date", "access_end_date", "notification_email")

class CustomUserAdmin(UserAdmin):
    form = JodahUserChangeForm
    add_form = JodahAdminUserCreationForm
    inlines = (UserAccessProfileInline,)
    _profile_inline_date_fields = ("access_start_date", "access_end_date", "notification_email")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "email")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "allow_add_users",
                    "allow_change_passwords",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "usable_password",
                    "password1",
                    "password2",
                    "allow_add_users",
                    "allow_change_passwords",
                ),
            },
        ),
    )

    def _may_access_auth_admin(self, request) -> bool:
        return staff_may_access_users_groups(admin_actor(request))

    def has_module_permission(self, request):
        return super().has_module_permission(request) and self._may_access_auth_admin(request)

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) and self._may_access_auth_admin(request)

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and self._may_access_auth_admin(request)

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and self._may_access_auth_admin(request)

    def has_add_permission(self, request):
        if not super().has_add_permission(request):
            return False
        return self._may_access_auth_admin(request) and staff_may_add_users(admin_actor(request))

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if not staff_may_change_passwords(admin_actor(request)):
            for name in (
                "is_superuser",
                "is_staff",
                "groups",
                "user_permissions",
                "allow_add_users",
                "allow_change_passwords",
            ):
                if name not in ro:
                    ro.append(name)
        return ro

    def save_model(self, request, obj, form, change):
        actor = admin_actor(request)
        if change and obj.pk and not staff_may_change_passwords(actor):
            prev = User.objects.get(pk=obj.pk)
            obj.is_superuser = prev.is_superuser
            obj.is_staff = prev.is_staff
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        """
        نموذج UserAccessProfile مرتبط بنموذج المستخدم؛ الحفظ الافتراضي للـ inline
        يعيد كتابة allow_add_users / allow_change_passwords بقيم قديمة في الذاكرة.
        نحدّث فقط حقول التواريخ والبريد من الـ inline.
        """
        if formset.model is not UserAccessProfile:
            return super().save_formset(request, form, formset, change)
        if not formset.is_valid():
            return
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for instance in instances:
            if instance.pk:
                instance.save(update_fields=list(self._profile_inline_date_fields))
            else:
                instance.save()

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        self._sync_user_access_profile_flags_from_user_form(form)

    def _sync_user_access_profile_flags_from_user_form(self, form):
        """بعد حفظ الـ inline و M2M؛ يطبّق أعلام الصلاحية من النموذج الرئيسي فقط."""
        if not getattr(form, "cleaned_data", None):
            return
        if not isinstance(form, (JodahUserChangeForm, JodahAdminUserCreationForm)):
            return
        if "allow_add_users" not in form.cleaned_data or "allow_change_passwords" not in form.cleaned_data:
            return
        user = form.instance
        if not user.pk:
            return
        prof, _ = UserAccessProfile.objects.get_or_create(user=user)
        prof.allow_add_users = form.cleaned_data["allow_add_users"]
        prof.allow_change_passwords = form.cleaned_data["allow_change_passwords"]
        prof.save(update_fields=["allow_add_users", "allow_change_passwords"])

    def get_fieldsets(self, request, obj=None):
        if not obj:
            return self.add_fieldsets
        fieldsets = list(super().get_fieldsets(request, obj))
        if obj and not staff_may_change_passwords(admin_actor(request)):
            first_heading, first_opts = fieldsets[0]
            first_fields = list(first_opts.get("fields", ()))
            if "password" in first_fields:
                first_fields = [f for f in first_fields if f != "password"]
                fieldsets[0] = (first_heading, {**first_opts, "fields": tuple(first_fields)})
        return fieldsets

    @method_decorator(sensitive_post_parameters())
    def user_change_password(self, request, id, form_url=""):
        if not staff_may_change_passwords(admin_actor(request)):
            raise PermissionDenied("غير مسموح لك بتغيير كلمات مرور المستخدمين.")
        return super().user_change_password(request, id, form_url)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "user_permissions":
            kwargs["queryset"] = Permission.objects.select_related("content_type").order_by(
                "content_type__app_label",
                "content_type__model",
                "codename",
            )
            kwargs["form_class"] = ReadablePermissionMultipleChoiceField
        return super().formfield_for_manytomany(db_field, request, **kwargs)


class CustomGroupAdmin(GroupAdmin):
    """صلاحيات المجموعات بنفس تنسيق المستخدمين."""

    def _may_edit_security(self, request):
        return (
            staff_may_access_users_groups(admin_actor(request))
            and staff_may_change_passwords(admin_actor(request))
        )

    def has_module_permission(self, request):
        return super().has_module_permission(request) and self._may_edit_security(request)

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) and self._may_edit_security(request)

    def has_add_permission(self, request):
        return super().has_add_permission(request) and self._may_edit_security(request)

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and self._may_edit_security(request)

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and self._may_edit_security(request)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "permissions":
            kwargs["queryset"] = Permission.objects.select_related("content_type").order_by(
                "content_type__app_label",
                "content_type__model",
                "codename",
            )
            kwargs["form_class"] = ReadablePermissionMultipleChoiceField
        return super().formfield_for_manytomany(db_field, request, **kwargs)


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

admin.site.unregister(Group)
admin.site.register(Group, CustomGroupAdmin)

# -----------------------------------------------------
# دالة معالجة الأرقام العشرية بأمان
# -----------------------------------------------------
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

def parse_decimal_safe(value: str, field_name: str) -> Decimal:
    if value is None:
        raise ValueError(f"{field_name} is empty")
    s = str(value).strip()
    if not s:
        raise ValueError(f"{field_name} is empty")
    s = s.translate(ARABIC_DIGITS)
    s = s.replace(",", "")
    s = re.sub(r"\s+", "", s)
    if not re.fullmatch(r"-?\d+(\.\d+)?", s):
        raise ValueError(f"{field_name} invalid format: {value!r}")
    try:
        return Decimal(s)
    except InvalidOperation:
        raise ValueError(f"{field_name} invalid number: {value!r}")

# أيقونات SVG مضمّنة (لا تعتمد على static — تعمل حتى لو حُجبت أنماط الخادم)
_WA_BRAND_SVG = (
    '<svg class="wa-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="26" height="26" '
    'fill="currentColor" aria-hidden="true"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.435 9.884-9.881 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"/></svg>'
)
_BACK_SVG = (
    '<svg class="back-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
    'fill="currentColor" aria-hidden="true"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/></svg>'
)

# أنماط إضافية (مع أنماط مضمّنة على العناصر أدناه حتى لو حُجبت وسوم style)
_ADMIN_WHATSAPP_PREVIEW_STYLES = """<style>
*,*::before,*::after{{box-sizing:border-box}}
html{{-webkit-text-size-adjust:100%}}
body{{font-family:'Segoe UI',Tahoma,'Arabic UI Text',Arial,sans-serif;margin:0;min-height:100vh;min-height:100dvh;padding:max(16px,env(safe-area-inset-top,0px)) max(14px,env(safe-area-inset-right,0px)) max(20px,env(safe-area-inset-bottom,0px)) max(14px,env(safe-area-inset-left,0px));display:flex;justify-content:center;align-items:flex-start;background:radial-gradient(ellipse 120% 80% at 50% -20%,#c7e9d8 0%,transparent 50%),linear-gradient(180deg,#eef2f7 0%,#e2e8f0 100%)}}
@media (min-width:700px){{body{{align-items:center;padding:32px 20px}}}}
.card{{width:100%;max-width:560px;margin:0 auto;border-radius:24px;overflow:hidden;background:#fff;box-shadow:0 25px 60px -15px rgba(15,23,42,.25),0 0 0 1px rgba(15,23,42,.06),inset 0 1px 0 rgba(255,255,255,.9)}}
.card-accent{{height:5px;background:linear-gradient(90deg,#128C7E,#25D366,#7CFF9A)}}
.card-head{{display:flex;align-items:flex-start;gap:16px;padding:22px 22px 18px;direction:rtl;border-bottom:1px solid #f1f5f9}}
.wa-badge{{flex-shrink:0;width:58px;height:58px;border-radius:18px;background:linear-gradient(145deg,#ecfdf5,#a7f3d0);color:#047857;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 14px rgba(16,185,129,.25)}}
.wa-badge .wa-svg{{width:32px;height:32px}}
.card-head h2{{margin:0;font-size:clamp(1.25rem,4.5vw,1.5rem);font-weight:800;color:#0f172a;line-height:1.3;letter-spacing:-.02em}}
.card-head .meta{{margin:10px 0 0;color:#64748b;font-size:clamp(.95rem,3.5vw,1.05rem);line-height:1.55}}
.msg{{margin:18px 20px 6px;padding:20px 18px;background:linear-gradient(180deg,#f8fafc 0%,#f1f5f9 100%);border:1px solid #e2e8f0;border-radius:18px;white-space:pre-wrap;font-size:clamp(1.06rem,3.8vw,1.14rem);line-height:1.9;direction:rtl;color:#1e293b;overflow-wrap:anywhere;word-break:break-word;-webkit-overflow-scrolling:touch}}
.actions{{padding:16px 20px 24px;display:flex;flex-direction:column;gap:14px}}
.btn-wa,.btn-back{{display:flex;align-items:center;justify-content:center;gap:12px;width:100%;text-decoration:none;font-weight:800;font-size:clamp(1.08rem,3.8vw,1.15rem);padding:18px 22px;border-radius:16px;min-height:58px;line-height:1.2;border:none;cursor:pointer;transition:filter .15s,transform .1s}}
.btn-wa{{background:linear-gradient(180deg,#2fe077,#25D366);color:#fff;box-shadow:0 6px 24px rgba(37,211,102,.45),inset 0 1px 0 rgba(255,255,255,.25)}}
.btn-wa:hover,.btn-wa:focus-visible{{filter:brightness(1.05)}}
.btn-wa:active{{transform:scale(.985)}}
.btn-wa .wa-svg{{flex-shrink:0;width:28px;height:28px;filter:drop-shadow(0 1px 1px rgba(0,0,0,.15))}}
.btn-back{{background:linear-gradient(180deg,#334155,#1e293b);color:#f8fafc;box-shadow:0 4px 16px rgba(15,23,42,.2),inset 0 1px 0 rgba(255,255,255,.08);border:1px solid #475569}}
.btn-back:hover,.btn-back:focus-visible{{filter:brightness(1.08)}}
.btn-back:active{{transform:scale(.985)}}
.btn-back .back-svg{{flex-shrink:0;width:24px;height:24px;opacity:.95}}
@media (min-width:480px){{.actions{{flex-direction:row;flex-wrap:wrap}}.btn-wa,.btn-back{{flex:1;min-width:min(100%,220px);width:auto}}}}
</style>"""


def _whatsapp_preview_response(
    *,
    page_title: str,
    heading: str,
    meta_html: str,
    safe_message: str,
    wa_url: str,
    changelist_url: str,
    back_button_title: str = "",
) -> HttpResponse:
    """صفحة معاينة واتساب: كارد + زران فقط (مراسلة + عودة للقائمة)."""
    wa = _WA_BRAND_SVG
    bk = _BACK_SVG
    title_attr = f' title="{escape(back_button_title)}"' if back_button_title else ""
    # أنماط مضمّنة: تظهر البطاقة والأزرار حتى لو حُجبت وسم &lt;style&gt; (CSP)
    html = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light">
<title>{page_title}</title>
{_ADMIN_WHATSAPP_PREVIEW_STYLES}
</head>
<body style="margin:0;min-height:100vh;min-height:100dvh;font-family:Tahoma,Arial,sans-serif;display:flex;justify-content:center;align-items:flex-start;padding:max(16px,env(safe-area-inset-top,0px)) 14px max(20px,env(safe-area-inset-bottom,0px));background:linear-gradient(180deg,#eef2f7,#e2e8f0);box-sizing:border-box;">
<div class="card" style="width:100%;max-width:560px;background:#fff;border-radius:24px;overflow:hidden;box-shadow:0 25px 60px -15px rgba(15,23,42,.25),0 0 0 1px rgba(15,23,42,.08);box-sizing:border-box;">
<div class="card-accent" style="height:5px;background:linear-gradient(90deg,#128C7E,#25D366,#86efac);"></div>
<div class="card-head" style="display:flex;align-items:flex-start;gap:16px;padding:22px 20px 16px;direction:rtl;border-bottom:1px solid #f1f5f9;box-sizing:border-box;">
<span class="wa-badge" style="flex-shrink:0;width:58px;height:58px;border-radius:18px;background:linear-gradient(145deg,#ecfdf5,#a7f3d0);color:#047857;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 14px rgba(16,185,129,.25);" aria-hidden="true">{wa}</span>
<div style="min-width:0;">
<h2 style="margin:0;font-size:1.35rem;font-weight:800;color:#0f172a;line-height:1.3;">{heading}</h2>
<p class="meta" style="margin:10px 0 0;color:#64748b;font-size:1rem;line-height:1.55;">{meta_html}</p>
</div>
</div>
<div class="msg" style="margin:16px 18px 8px;padding:18px 16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:18px;white-space:pre-wrap;font-size:1.08rem;line-height:1.9;direction:rtl;color:#1e293b;overflow-wrap:break-word;box-sizing:border-box;">{safe_message}</div>
<div class="actions" style="padding:14px 18px 22px;display:flex;flex-direction:column;gap:14px;box-sizing:border-box;">
<a href="{wa_url}" target="_blank" rel="noopener noreferrer" class="btn-wa" style="display:flex;align-items:center;justify-content:center;gap:12px;width:100%;box-sizing:border-box;background:linear-gradient(180deg,#2fe077,#25D366);color:#fff;text-decoration:none;font-weight:800;font-size:1.1rem;padding:18px 20px;border-radius:16px;min-height:58px;box-shadow:0 6px 22px rgba(37,211,102,.4);border:none;">{wa}<span>إرسال عبر واتساب</span></a>
<a href="{changelist_url}" class="btn-back"{title_attr} style="display:flex;align-items:center;justify-content:center;gap:12px;width:100%;box-sizing:border-box;background:linear-gradient(180deg,#475569,#1e293b);color:#f8fafc;text-decoration:none;font-weight:800;font-size:1.1rem;padding:18px 20px;border-radius:16px;min-height:58px;border:1px solid #64748b;box-shadow:0 4px 16px rgba(15,23,42,.2);">{bk}<span>العودة</span></a>
</div>
</div>
</body>
</html>"""
    return HttpResponse(html, content_type="text/html; charset=utf-8")

# -----------------------------------------------------
# واجهة إدارة الصور (Inline)
# -----------------------------------------------------
class PropertyRequestImageInline(admin.TabularInline):
    model = PropertyRequestImage
    extra = 0
    readonly_fields = ("thumb",)
    fields = ("thumb", "image", "sort_order", "is_cover")

    @admin.display(description="مصغّر")
    def thumb(self, obj):
        if not obj or not getattr(obj, "pk", None):
            return "—"
        img = getattr(obj, "image", None)
        if img and hasattr(img, "url"):
            return format_html(
                '<img src="{}" style="height:60px;width:90px;object-fit:cover;border-radius:6px;border:1px solid #ddd;" />',
                img.url,
            )
        return "—"

# -----------------------------------------------------
# واجهة إدارة العقارات (Property)
# -----------------------------------------------------
@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = (
        'listing_id', 'full_name', 'property_type', 'offer_type', 'price', 
        'performance_dashboard_link', 'status', 'visibility', 
        'qr_code_link', 'inquiry_count', 'created_at'
    )
    list_filter = (
        'visibility', 'city', 'district', 'property_type', 
        'offer_type', 'status', 'category', 'negotiation_status', 'show_price_to_visitors'
    )
    search_fields = ('full_name', 'phone', 'city', 'district', 'listing_id')
    ordering = ('-created_at',)
    readonly_fields = (
        'listing_id',
        'inquiry_count',
        'created_at',
        'qr_code_link',
        'performance_dashboard_link',
        'ai_copy_btn',
    )

    @admin.display(description="🖨️ طباعة QR")
    def qr_code_link(self, obj):
        if not obj.pk:
            return "-"
        url = reverse("listings:property_qr", args=[obj.pk])
        style = "white-space: nowrap; display: inline-block; margin: 4px 0; padding: 4px 8px; line-height: 1.2; font-size: 0.75rem; background-color: #ffffff; color: #C9A24A; border: 1px solid #C9A24A; border-radius: 4px; font-weight: bold;"
        return format_html('<a class="button" href="{}" target="_blank" style="{}">🖨️ طباعة QR</a>', url, style)

    @admin.display(description="📊 أداء العقار")
    def performance_dashboard_link(self, obj):
        if not obj.pk:
            return "-"
        url = reverse("listings:owner-performance", args=[obj.pk])
        style = "white-space: nowrap; display: inline-block; margin: 4px 0; padding: 4px 8px; font-size: 0.75rem; background-color: #0f172a; color: #ffffff; border-radius: 4px; font-weight: bold;"
        return format_html('<a class="button" href="{}" target="_blank" style="{}">📊 أداء العقار</a>', url, style)
    qr_code_link.short_description = "بطاقة QR"

    @admin.display(description="حالة السعر")
    def price_visibility_status(self, obj):
        icon = "✅" if obj.show_price_to_visitors else "❌"
        label = "ظاهر" if obj.show_price_to_visitors else "مخفي"
        return format_html('{} {}', icon, label)
    @admin.display(description="الموقع")
    def map_visibility_status(self, obj: Property) -> str:
        map_url = (getattr(obj, "map_url", "") or "").strip()
        if not map_url:
            return "غير متوفر"
        return "ظاهر" if obj.show_map_to_visitors else "مخفي"

    @admin.display(description="الذكاء الاصطناعي")
    def ai_copy_btn(self, obj):
        if not obj.pk:
            return "يجب حفظ العقار أولاً"
        
        btn_html = f"""
        <div style="display: flex; align-items: center; gap: 10px;">
            <button type="button" class="button" onclick="generateAICopy({obj.pk})" 
                style="background: #C9A24A; color: white; border: none; padding: 10px 20px; border-radius: 6px; font-weight: bold; cursor: pointer; display: flex; align-items: center; gap: 8px;">
                <i class="fas fa-magic"></i> توليد وصف إبداعي (AI)
            </button>
            <span id="ai-loading" style="display: none; color: #C9A24A;"><i class="fas fa-spinner fa-spin"></i> جاري التوليد...</span>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
        <script>
        window.generateAICopy = async function(propId) {{
            const loading = document.getElementById('ai-loading');
            loading.style.display = 'inline';
            
            try {{
                const response = await fetch('/api/admin/generate-ai-copy/', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                    }},
                    body: JSON.stringify({{ property_id: propId }})
                }});
                
                const data = await response.json();
                loading.style.display = 'none';
                
                if (data.success) {{
                    Swal.fire({{
                        title: '✨ الوصف الإبداعي المقترح',
                        html: `<textarea id="ai-copy-text" style="width: 100%; height: 300px; padding: 10px; border-radius: 8px; border: 1px solid #ddd; font-family: inherit; line-height: 1.6; background: #fafafa; direction: rtl;">${{data.content}}</textarea>`,
                        showCancelButton: true,
                        confirmButtonText: '📋 نسخ النص',
                        cancelButtonText: 'إغلاق',
                        confirmButtonColor: '#C9A24A',
                        preConfirm: () => {{
                            const text = document.getElementById('ai-copy-text').value;
                            navigator.clipboard.writeText(text);
                            Swal.fire('تم النسخ!', '', 'success');
                        }}
                    }});
                }} else {{
                    Swal.fire('خطأ', data.error || 'فشل في توليد النص', 'error');
                }}
            }} catch (e) {{
                loading.style.display = 'none';
                Swal.fire('خطأ', 'حدثت مشكلة في الاتصال بالسيرفر', 'error');
            }}
        }};
        </script>
        """
        return mark_safe(btn_html)

    fieldsets = (
        ("بيانات الملاك", {'fields': ('full_name', 'phone')}),
        ("بيانات ووصف العقار", {'fields': ('listing_id', 'status', 'visibility', 'map_url', 'show_map_to_visitors', 'video_url', 'video_enabled', 'owner_notes', 'ai_copy_btn')}),
        ("بيانات العرض والموقع", {'fields': ('city', 'district', 'offer_type', 'property_type', 'category')}),
        ("تفاصيل المبيع", {'fields': ('area', 'price', 'negotiation_status', 'show_price_to_visitors', 'inquiry_count')}),
        ("المواصفات الفنية", {'fields': ('property_age', 'floors', 'rooms', 'apartments', 'bathrooms')}),
        ("صور العقار", {'fields': ('cover_image_slot', 'image1', 'image2', 'image3', 'image4', 'image5', 'image6', 'image7', 'image8', 'image9', 'image10')}),
        ("بيانات بطاقة QR", {'fields': ('val_license', 'ad_number')}),
    )

    def view_on_site(self, obj):
        return reverse('listings:property-detail', kwargs={'pk': obj.pk})

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        from django.forms import TextInput, Textarea
        if db_field.name == 'map_url':
            kwargs['widget'] = TextInput(attrs={
                'class': 'vTextField', 
                'style': 'width: 80%; min-width: 400px; text-align: left; direction: ltr;'
            })
        elif db_field.name == 'owner_notes':
            kwargs['widget'] = Textarea(attrs={
                'class': 'vLargeTextField', 
                'style': 'width: 80%; min-width: 400px; height: 150px; resize: vertical;'
            })
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    # الأكشنات (Actions) — يجب تضمين delete_selected صراحةً عند تعريف actions
    actions = [
        'make_published', 'make_hidden',
        'show_prices_action', 'hide_prices_action',
        'show_map_action', 'hide_map_action',
        'publish_to_haraj_job_action',
        'post_to_x_action', 'post_to_wa_action',
        'copy_property_text_action', 'generate_ai_copy_action',
        'export_to_sheets_action',
        'delete_selected',
    ]

    def _build_haraj_payload(self, obj: Property) -> dict:
        # Business rule: always publish price as 1 on Haraj.
        # Some marketers do not disclose the real property price.
        price_value = 1

        title = f"{obj.offer_type} {obj.property_type} في {obj.city} - {obj.district or ''}".strip(" -")
        description_lines = [
            f"{obj.offer_type} {obj.property_type}",
            f"المالك: {obj.full_name}" if obj.full_name else "",
            "السعر: 1 ريال",
            f"الموقع: {obj.city} - {obj.district}" if obj.city or obj.district else "",
            f"المساحة: {obj.area} م²" if obj.area else "",
            f"رقم العرض: #{obj.listing_id}" if obj.listing_id else "",
            obj.owner_notes or "",
        ]
        description = "\n".join([line for line in description_lines if line]).strip()

        image_paths = []
        for img in (obj.all_images or []):
            # Cloudinary links are remote URLs; local runner can decide how to fetch/download later.
            try:
                if hasattr(img, "url") and img.url:
                    image_paths.append(img.url)
            except Exception:
                continue

        return {
            "title": title or (obj.full_name or "عرض عقاري"),
            "description": description or "وصف العقار غير متوفر حالياً.",
            "price": price_value,
            "transaction_type": "rent" if (obj.offer_type or "").strip() == "إيجار" else "sale",
            "city": obj.city or "",
            "district": obj.district or "",
            "property_type": obj.property_type or "",
            "area": str(obj.area or "").strip(),
            "property_age": str(obj.property_age or "").strip(),
            # Defaults used by Haraj UI sections if payload lacks explicit values.
            "advertiser_type": "مالك",
            "buyer_type": "سكني",
            "facade": "شمالية",
            "image_paths": image_paths,
            "reference_id": str(obj.pk),
        }

    @admin.action(description="📤 تصدير إلى قوقل شيت")
    def export_to_sheets_action(self, request, queryset):
        count = queryset.count()
        for prop in queryset:
            sync_published_property_async(prop.pk)
        
        self.message_user(
            request, 
            f"جاري تصدير {count} عقار إلى قوقل شيت في الخلفية...", 
            messages.SUCCESS
        )

    @admin.action(description="🤖 إرسال للنشر الآلي في حراج (Publishing Job)")
    def publish_to_haraj_job_action(self, request, queryset):
        tenant_id = getattr(settings, "PUBLISHING_DEFAULT_TENANT_ID", "demo-tenant")
        created = 0
        failed = 0
        failure_reasons = []
        for prop in queryset:
            try:
                PublisherService.submit(
                    PublishRequest(
                        tenant_id=tenant_id,
                        provider="haraj",
                        payload=self._build_haraj_payload(prop),
                        created_by_id=getattr(request.user, "id", None),
                        source_model="listings.Property",
                        source_object_id=str(prop.pk),
                        priority=5,
                        max_attempts=3,
                    )
                )
                created += 1
            except Exception as exc:
                failed += 1
                failure_reasons.append(f"#{getattr(prop, 'listing_id', prop.pk)}: {str(exc)}")

        if created:
            self.message_user(
                request,
                f"تم إنشاء {created} مهمة نشر آلي في حراج (tenant: {tenant_id}).",
                messages.SUCCESS,
            )
        if failed:
            reason_text = ""
            if failure_reasons:
                reason_text = f" | السبب: {failure_reasons[0]}"
            self.message_user(
                request,
                f"فشل إنشاء {failed} مهمة. تحقق من إعداد ChannelConfig أو payload.{reason_text}",
                messages.ERROR,
            )

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        from listings.services.dashboard_service import DashboardService
        extra_context['header_stats'] = DashboardService.get_property_header_stats()
        
        cl = self.get_changelist_instance(request)
        results = []
        for obj in cl.result_list:
            results.append({
                'id': obj.id,
                'pk': obj.pk,
                'listing_id': obj.listing_id,
                'title': obj.full_name,
                'property_type': obj.property_type,
                'offer_type': obj.offer_type,
                'price': f"{float(obj.price):,.0f}" if obj.price else "—",
                'city': obj.city,
                'district': obj.district,
                'date': obj.created_at.strftime('%Y-%m-%d'),
                'status_html': self.get_status_badge(obj),
                'edit_url': reverse('admin:listings_property_change', args=[obj.pk]),
                'qr_url': reverse('listings:property_qr', args=[obj.pk]),
                'is_new': obj.created_at.date() == timezone.now().date(),
            })
        extra_context['results'] = results
        return super().changelist_view(request, extra_context=extra_context)

    def get_status_badge(self, obj):
        colors = {
            'متاح': ('#22C55E', '#FFFFFF'),
            'مباع': ('#EF4444', '#FFFFFF'),
            'مؤجر': ('#3B82F6', '#FFFFFF'),
            'قيد التفاوض': ('#F59E0B', '#FFFFFF'),
            'انتهت الفرصة': ('#6B7280', '#FFFFFF'),
        }
        bg, text = colors.get(obj.status, ('#6B7280', '#FFFFFF'))
        style = f"display: inline-block; padding: 4px 10px; border-radius: 8px; font-weight: 700; font-size: 0.75rem; background-color: {bg}; color: {text};"
        return format_html('<span style="{}">{}</span>', style, obj.status)

    @admin.action(description="نشر العروض المحددة")
    def make_published(self, request, queryset):
        updated = queryset.update(visibility='منشور')
        self.message_user(request, f"تم نشر {updated} عقار بنجاح.", messages.SUCCESS)

    @admin.action(description="إخفاء العروض المحددة")
    def make_hidden(self, request, queryset):
        updated = queryset.update(visibility='مخفي')
        self.message_user(request, f"تم إخفاء {updated} عقار بنجاح.", messages.SUCCESS)

    @admin.action(description="إظهار السعر للزوار")
    def show_prices_action(self, request, queryset):
        updated = queryset.update(show_price_to_visitors=True)
        self.message_user(request, f"تم إظهار السعر لـ {updated} عقار.", messages.SUCCESS)

    @admin.action(description="إخفاء السعر عن الزوار")
    def hide_prices_action(self, request, queryset):
        updated = queryset.update(show_price_to_visitors=False)
        self.message_user(request, f"تم إخفاء السعر لـ {updated} عقار.", messages.SUCCESS)

    @admin.action(description="إظهار الخريطة للزوار")
    def show_map_action(self, request, queryset):
        updated = queryset.update(show_map_to_visitors=True)
        self.message_user(request, f"تم إظهار الخريطة لـ {updated} عقار.", messages.SUCCESS)

    @admin.action(description="إخفاء الخريطة عن الزوار")
    def hide_map_action(self, request, queryset):
        updated = queryset.update(show_map_to_visitors=False)
        self.message_user(request, f"تم إخفاء الخريطة لـ {updated} عقار.", messages.SUCCESS)

    @admin.action(description="نشر العقار المختار على X (تويتر)")
    def post_to_x_action(self, request, queryset):
        from .x_utils import post_property_to_x
        from django.http import HttpResponse
        
        if queryset.count() > 1:
            self.message_user(request, "يرجى اختيار عقار واحد فقط للنشر على X.", messages.WARNING)
            return
            
        property_obj = queryset.first()
        success, url_or_msg = post_property_to_x(property_obj, request)
        
        if success:
            # We use a user-interaction HTML response to open the X link in a NEW tab,
            # to avoid automatic popup blockers, and then allow returning to the admin.
            base_url = request.build_absolute_uri("/admin/listings/property/")
            html = f"""
            <!DOCTYPE html>
            <html dir="rtl" lang="ar">
            <head>
                <meta charset="utf-8">
                <title>نشر على X</title>
                <style>
                    body {{ font-family: Tahoma, Arial, sans-serif; background: #f8f9fa; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
                    .box {{ background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); text-align: center; max-width: 500px; width: 90%; }}
                    h2 {{ color: #333; margin-bottom: 20px; }}
                    p {{ color: #666; margin-bottom: 30px; font-size: 16px; line-height: 1.6; }}
                    .btn {{ display: inline-block; padding: 12px 25px; background: #1da1f2; color: white; text-decoration: none; border-radius: 50px; font-weight: bold; font-size: 16px; transition: 0.3s; margin: 5px; }}
                    .btn:hover {{ background: #0c85d0; }}
                    .btn-secondary {{ background: #6c757d; }}
                    .btn-secondary:hover {{ background: #5a6268; }}
                </style>
            </head>
            <body>
                <div class="box">
                    <h2>✅ جاهز للنشر</h2>
                    <p>تم تحضير محتوى التغريدة بنجاح. اضغط على الزر أدناه ليتم فتح منصة <strong>X (تويتر)</strong> في نافذة جديدة والتغريد فوراً.</p>
                    <a href="{url_or_msg}" target="_blank" class="btn" onclick="setTimeout(function(){{ window.location.href='{base_url}'; }}, 1500);">📤 انشر الآن على X</a>
                    <a href="{base_url}" class="btn btn-secondary">إلغاء والعودة</a>
                </div>
            </body>
            </html>
            """
            return HttpResponse(html)
        else:
            self.message_user(request, url_or_msg, messages.ERROR)

    @admin.action(description="نشر العرض على الواتساب")
    def post_to_wa_action(self, request, queryset):
        from .wa_utils import post_property_to_whatsapp
        from django.http import HttpResponse
        
        if queryset.count() > 1:
            self.message_user(request, "يرجى اختيار عقار واحد فقط للنشر على الواتساب.", messages.WARNING)
            return
            
        property_obj = queryset.first()
        success, url_or_msg = post_property_to_whatsapp(property_obj, request)
        
        if success:
            base_url = request.build_absolute_uri("/admin/listings/property/")
            html = f"""
            <!DOCTYPE html>
            <html dir="rtl" lang="ar">
            <head>
                <meta charset="utf-8">
                <title>نشر على واتساب</title>
                <style>
                    body {{ font-family: Tahoma, Arial, sans-serif; background: #f8f9fa; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
                    .box {{ background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); text-align: center; max-width: 500px; width: 90%; }}
                    h2 {{ color: #25D366; margin-bottom: 20px; }}
                    p {{ color: #666; margin-bottom: 30px; font-size: 16px; line-height: 1.6; }}
                    .btn {{ display: inline-block; padding: 12px 25px; background: #25D366; color: white; text-decoration: none; border-radius: 50px; font-weight: bold; font-size: 16px; transition: 0.3s; margin: 5px; }}
                    .btn:hover {{ background: #1ebd5c; }}
                    .btn-secondary {{ background: #6c757d; }}
                    .btn-secondary:hover {{ background: #5a6268; }}
                </style>
            </head>
            <body>
                <div class="box">
                    <h2>✅ جاهز للنشر على واتساب</h2>
                    <p>تم تحضير محتوى الرسالة بنجاح. اضغط على الزر أدناه ليتم فتح <strong>واتساب</strong> وإرسال الرسالة فوراً.</p>
                    <a href="{url_or_msg}" target="_blank" class="btn" onclick="setTimeout(function(){{ window.location.href='{base_url}'; }}, 1500);">📲 انشر الآن على واتساب</a>
                    <a href="{base_url}" class="btn btn-secondary">إلغاء والعودة</a>
                </div>
            </body>
            </html>
            """
            return HttpResponse(html)
        else:
            self.message_user(request, url_or_msg, messages.ERROR)

    @admin.action(description="نسخ العرض للمنصات العقارية (حراج وغيرها)")
    def copy_property_text_action(self, request, queryset):
        from .copy_utils import generate_property_copy_text
        from django.http import HttpResponse
        import json
        
        if queryset.count() > 1:
            self.message_user(request, "يرجى اختيار عقار واحد فقط للنسخ.", messages.WARNING)
            return
            
        property_obj = queryset.first()
        success, text_or_msg = generate_property_copy_text(property_obj, request)
        
        if success:
            base_url = request.build_absolute_uri("/admin/listings/property/")
            # Escape the text for JavaScript compatibility safely
            escaped_text = text_or_msg.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$').replace('\n', '\\n')
            
            html = f"""
            <!DOCTYPE html>
            <html dir="rtl" lang="ar">
            <head>
                <meta charset="utf-8">
                <title>نسخ إعلان العقار</title>
                <style>
                    body {{ font-family: Tahoma, Arial, sans-serif; background: #f8f9fa; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
                    .box {{ background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); width: 90%; max-width: 600px; text-align: center; }}
                    h2 {{ color: #C9A24A; margin-bottom: 20px; }}
                    p {{ color: #666; margin-bottom: 20px; font-size: 16px; line-height: 1.6; }}
                    textarea {{ width: 100%; height: 250px; padding: 15px; border: 1px solid #ddd; border-radius: 8px; font-family: inherit; font-size: 15px; line-height: 1.8; resize: vertical; margin-bottom: 20px; background: #fafafa; }}
                    .btn {{ display: inline-block; padding: 12px 25px; background: #0B1B3A; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 16px; transition: 0.3s; margin: 5px; cursor: pointer; border: none; }}
                    .btn:hover {{ background: #C9A24A; }}
                    .btn-secondary {{ background: #6c757d; }}
                    .btn-secondary:hover {{ background: #5a6268; }}
                    .success-msg {{ display: none; color: #22C55E; font-weight: bold; margin-top: 15px; }}
                </style>
            </head>
            <body>
                <div class="box">
                    <h2>📋 إعلان جاهز للنسخ والتسويق</h2>
                    <p>قمنا بتجهيز تفاصيل العقار بتنسيق مناسب للنشر على منصات مثل <strong>حراج، عقار، وغيرها</strong>.</p>
                    
                    <textarea id="adText" readonly>{text_or_msg}</textarea>
                    
                    <button id="copyBtn" class="btn">📋 نسخ النص والصور</button>
                    <a href="{base_url}" class="btn btn-secondary">العودة للوحة التحكم</a>
                    
                    <div id="successMsg" class="success-msg">✅ تم نسخ النص بنجاح! يمكنك الآن لصقه في المنصة المطلوبة. (يتم التوجيه للوحة التحكم...)</div>
                </div>

                <script>
                    document.getElementById('copyBtn').addEventListener('click', function() {{
                        const textArea = document.getElementById('adText');
                        textArea.select();
                        textArea.setSelectionRange(0, 99999); // For mobile devices
                        
                        try {{
                            // Modern approach
                            navigator.clipboard.writeText(textArea.value).then(() => {{
                                showSuccess();
                            }}).catch(() => {{
                                // Fallback
                                document.execCommand('copy');
                                showSuccess();
                            }});
                        }} catch (err) {{
                            document.execCommand('copy');
                            showSuccess();
                        }}
                    }});
                    
                    function showSuccess() {{
                        document.getElementById('successMsg').style.display = 'block';
                        setTimeout(function() {{
                            window.location.href = '{base_url}';
                        }}, 2000);
                    }}
                </script>
            </body>
            </html>
            """
            return HttpResponse(html)
        else:
            self.message_user(request, text_or_msg, messages.ERROR)

    @admin.action(description="✨ توليد وصف إبداعي بالذكاء الاصطناعي (AI)")
    def generate_ai_copy_action(self, request, queryset):
        from .services.ai_utils import generate_creative_description
        from django.http import HttpResponse
        
        if queryset.count() > 1:
            self.message_user(request, "يرجى اختيار عقار واحد فقط لتوليد النص.", messages.WARNING)
            return
            
        property_obj = queryset.first()
        success, content_or_msg = generate_creative_description(property_obj)
        
        if success:
            base_url = request.build_absolute_uri("/admin/listings/property/")
            # Escape for JS
            escaped_content = content_or_msg.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$').replace('\n', '\\n')
            
            html = f"""
            <!DOCTYPE html>
            <html dir="rtl" lang="ar">
            <head>
                <meta charset="utf-8">
                <title>وصف إبداعي بالذكاء الاصطناعي</title>
                <style>
                    body {{ font-family: Tahoma, Arial, sans-serif; background: #f8f9fa; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
                    .box {{ background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); width: 90%; max-width: 600px; text-align: center; }}
                    h2 {{ color: #C9A24A; margin-bottom: 20px; }}
                    p {{ color: #666; margin-bottom: 20px; font-size: 16px; line-height: 1.6; }}
                    textarea {{ width: 100%; height: 300px; padding: 15px; border: 1px solid #ddd; border-radius: 8px; font-family: inherit; font-size: 15px; line-height: 1.8; resize: vertical; margin-bottom: 20px; background: #fafafa; }}
                    .btn {{ display: inline-block; padding: 12px 25px; background: #C9A24A; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 16px; transition: 0.3s; margin: 5px; cursor: pointer; border: none; }}
                    .btn:hover {{ background: #0B1B3A; }}
                    .btn-secondary {{ background: #6c757d; }}
                    .btn-secondary:hover {{ background: #5a6268; }}
                    .success-msg {{ display: none; color: #22C55E; font-weight: bold; margin-top: 15px; }}
                </style>
            </head>
            <body>
                <div class="box">
                    <h2>✨ وصف إبداعي مقترح (AI)</h2>
                    <p>تم توليد هذا النص بواسطة الذكاء الاصطناعي بناءً على مواصفات العقار.</p>
                    
                    <textarea id="aiText" readonly>{content_or_msg}</textarea>
                    
                    <button id="copyBtn" class="btn">📋 نسخ النص</button>
                    <a href="{base_url}" class="btn btn-secondary">العودة للوحة التحكم</a>
                    
                    <div id="successMsg" class="success-msg">✅ تم نسخ النص بنجاح!</div>
                </div>

                <script>
                    document.getElementById('copyBtn').addEventListener('click', function() {{
                        const textArea = document.getElementById('aiText');
                        textArea.select();
                        try {{
                            navigator.clipboard.writeText(textArea.value).then(() => {{
                                showSuccess();
                            }});
                        }} catch (err) {{
                            document.execCommand('copy');
                            showSuccess();
                        }}
                    }});
                    
                    function showSuccess() {{
                        document.getElementById('successMsg').style.display = 'block';
                    }}
                </script>
            </body>
            </html>
            """
            return HttpResponse(html)
        else:
            self.message_user(request, content_or_msg, messages.ERROR)

# -----------------------------------------------------
# واجهة إدارة طلبات تسويق العقار (PropertyOffer)
# -----------------------------------------------------
@admin.register(PropertyOffer)
class PropertyOfferAdmin(admin.ModelAdmin):
    inlines = [PropertyRequestImageInline]
    list_display = ("id", "status_badge", "owner_name", "phone", "city", "property_type", "listing_type", "assigned_to", "created_at")
    list_filter = ("status", "city", "listing_type", "category", "assigned_to")
    search_fields = ("owner_name", "phone", "city", "neighborhood")
    ordering = ("-created_at",)
    fieldsets = (
        ("بيانات الملاك", {"fields": ("owner_name", "phone", "whatsapp_url")}),
        ("تفاصيل العقار", {"fields": ("city","neighborhood","property_type","property_age","listing_type","category","area","price","floors","apartments","rooms","bathrooms")}),
        ("الوسائط", {"fields": ("video_link", "video_enabled", "google_map")}),
        ("ملاحظات وحالة", {"fields": ("owner_notes", "status", "assigned_to")}),
    )

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        # Fetch staff users for assignment dropdown
        from django.contrib.auth.models import User
        from listings.services.dashboard_service import DashboardService
        
        raw_marketers = User.objects.filter(is_staff=True).only("id", "first_name", "last_name", "username")
        marketers_data = []
        for m in raw_marketers:
            name = m.get_full_name() or m.username
            marketers_data.append({
                'id': m.id,
                'name': name,
                'initial': name[0].upper() if name else "?"
            })
        extra_context['marketers'] = marketers_data
        extra_context['header_stats'] = DashboardService.get_offer_header_stats()
        
        # We need the changelist to get the queryset after filters/search
        cl = self.get_changelist_instance(request)
        results = []
        for obj in cl.result_list:
            results.append({
                'id': obj.id,
                'owner_name': obj.owner_name,
                'phone': obj.phone,
                'city': obj.city,
                'neighborhood': obj.neighborhood,
                'date': obj.created_at.strftime('%Y-%m-%d'),
                'status_html': self.status_badge(obj),
                'assigned_to': (obj.assigned_to.get_full_name() or obj.assigned_to.username) if obj.assigned_to else "غير مسند",
                'is_new': obj.created_at.date() == timezone.now().date(),
                'edit_url': reverse('admin:listings_propertyoffer_change', args=[obj.pk])
            })
        extra_context['results'] = results
        return super().changelist_view(request, extra_context=extra_context)

    def status_badge(self, obj: PropertyOffer):
        colors = {
            PropertyOffer.Status.NEW: ('rgba(212, 175, 55, 0.15)', '#D4AF37', 'جديد'),
            PropertyOffer.Status.CONTACTED: ('rgba(6, 182, 212, 0.18)', '#0891B2', 'تم التواصل'),
            PropertyOffer.Status.UNDER_REVIEW: ('rgba(59, 130, 246, 0.15)', '#3B82F6', 'قيد المراجعة'),
            PropertyOffer.Status.OWNER_REVIEW: ('rgba(139, 92, 246, 0.15)', '#8B5CF6', 'مراجعة صاحب العقار'),
            PropertyOffer.Status.PUBLISHED: ('rgba(16, 185, 129, 0.15)', '#10B981', 'تم نشره'),
            PropertyOffer.Status.REJECTED: ('rgba(239, 68, 68, 0.15)', '#EF4444', 'مرفوض'),
        }
        # Get from choices or default
        status_info = colors.get(obj.status, ('rgba(107, 114, 128, 0.15)', '#6B7280', obj.get_status_display()))
        bg, text, label = status_info
        
        # Consistent style for all admin badges
        style = f"display: inline-block; padding: 6px 14px; border-radius: 8px; font-weight: 700; font-size: 0.85rem; text-align: center; min-width: 80px; background-color: {bg} !important; color: {text} !important;"
        if obj.status == PropertyOffer.Status.NEW:
            style += " border: 1px solid rgba(212, 175, 55, 0.3);"
        
        return format_html('<span style="{}">{}</span>', style, label)

    actions = [
        "generate_whatsapp_message",
        "mark_as_contacted",
        "mark_as_reviewing",
        "mark_as_owner_review",
        "publish_as_property",
        "mark_as_rejected",
        "assign_to_me",
        "assign_to_marketer",
        "delete_selected",
    ]
    co_admin_assignment_actions = ("assign_to_marketer", "assign_to_me")

    @admin.action(description="💬 رسالة واتساب للمالك (طلب تسويق)")
    def generate_whatsapp_message(self, request, queryset):
        from urllib.parse import quote

        if queryset.count() > 1:
            self.message_user(request, "⚠️ اختر طلب تسويق واحداً فقط.", messages.WARNING)
            return
        offer = queryset.first()
        phone = (offer.phone or "").strip()
        if not phone:
            self.message_user(request, "⚠️ لا يوجد رقم جوال للمالك في هذا الطلب.", messages.WARNING)
            return
        digits = "".join(c for c in phone if c.isdigit())
        if digits.startswith("0"):
            digits = "966" + digits[1:]
        elif not digits.startswith("966") and len(digits) == 9:
            digits = "966" + digits
        if len(digits) < 10:
            self.message_user(request, "⚠️ رقم الجوال غير صالح.", messages.WARNING)
            return

        city = offer.city or "—"
        nh = offer.neighborhood or "—"
        pt = offer.property_type or "—"
        lt = offer.listing_type or "—"
        area = offer.area or "—"
        price = offer.price or "—"
        owner = offer.owner_name or "المالك الكريم"
        message = (
            f"السلام عليكم {owner} 👋\n\n"
            f"نود المتابعة معكم بخصوص طلب تسويق العقار رقم *#{offer.pk}*.\n"
            f"• {city} — {nh}\n"
            f"• {pt} | {lt}\n"
            f"• المساحة: {area} | السعر: {price}\n\n"
            f"نرجو التواصل معنا لإكمال الإجراءات.\n"
            f"جودة المستقبل العقارية 🏠"
        )
        wa_url = f"https://wa.me/{digits}?text={quote(message)}"
        safe_msg = escape(message)
        changelist_url = request.build_absolute_uri(reverse("admin:listings_propertyoffer_changelist"))
        return _whatsapp_preview_response(
            page_title=f"واتساب المالك – طلب #{offer.pk}",
            heading="رسالة واتساب جاهزة للمالك",
            meta_html=f"الطلب: <strong>#{offer.pk}</strong> | الجوال: <strong>{escape(phone)}</strong>",
            safe_message=safe_msg,
            wa_url=wa_url,
            changelist_url=changelist_url,
            back_button_title="العودة إلى قائمة طلبات تسويق العقارات",
        )

    @admin.action(description="📞 تم التواصل مع المالك")
    def mark_as_contacted(self, request, queryset):
        updated = queryset.exclude(
            status__in=[PropertyOffer.Status.PUBLISHED, PropertyOffer.Status.REJECTED]
        ).update(status=PropertyOffer.Status.CONTACTED)
        self.message_user(
            request,
            f"تم تحديث {updated} طلب إلى «تم التواصل».",
            messages.SUCCESS,
        )

    @admin.action(description="👤 إسناد الطلبات لمسوق معين")
    def assign_to_marketer(self, request, queryset):
        marketer_id = request.POST.get('marketer_id')
        if not marketer_id:
            self.message_user(request, "يرجى اختيار مسوق من القائمة المنسدلة.", messages.WARNING)
            return
        
        from django.contrib.auth.models import User
        try:
            marketer = User.objects.get(id=marketer_id)
            updated = queryset.update(assigned_to=marketer)
            self.message_user(request, f"تم إسناد {updated} طلبات إلى {marketer.get_full_name() or marketer.username} بنجاح.", messages.SUCCESS)
        except User.DoesNotExist:
            self.message_user(request, "المسوق المختار غير موجود.", messages.ERROR)

    @admin.action(description="🔍 مراجعة الطلبات المختارة")
    def mark_as_reviewing(self, request, queryset):
        updated = queryset.update(status=PropertyOffer.Status.UNDER_REVIEW)
        self.message_user(request, f"تم تحديث {updated} طلب إلى 'قيد المراجعة'.", messages.SUCCESS)

    @admin.action(description="🏠 مراجعة صاحب العقار")
    def mark_as_owner_review(self, request, queryset):
        updated = queryset.update(status=PropertyOffer.Status.OWNER_REVIEW)
        self.message_user(request, f"تم تحديث {updated} طلب إلى 'مراجعة صاحب العقار'.", messages.SUCCESS)

    @admin.action(description="❌ رفض الطلبات المختارة")
    def mark_as_rejected(self, request, queryset):
        updated = queryset.update(status=PropertyOffer.Status.REJECTED)
        self.message_user(request, f"تم تحديث {updated} طلب إلى 'مرفوض'.", messages.WARNING)

    @admin.action(description="إسناد الطلبات المختارة لي")
    def assign_to_me(self, request, queryset):
        updated = queryset.update(assigned_to=request.user)
        self.message_user(request, f"تم إسناد {updated} طلبات إليك بنجاح.", messages.SUCCESS)

    @admin.action(description="تحويل الطلب إلى عقار (إنشاء Property جديد)")
    def publish_as_property(self, request, queryset):
        published = 0
        skipped = 0
        with transaction.atomic():
            for offer in queryset.select_for_update():
                existing = Property.objects.filter(source_offer=offer).only("id").first()
                if existing:
                    skipped += 1
                    continue
                try:
                    area_val = parse_decimal_safe(offer.area, "area")
                    price_val = parse_decimal_safe(offer.price, "price")
                except ValueError as e:
                    skipped += 1
                    self.message_user(request, f"خطأ في الطلب #{offer.id}: {e}", messages.ERROR)
                    continue

                prop = Property.objects.create(
                    source_offer=offer, full_name=offer.owner_name, phone=offer.phone,
                    city=offer.city, district=offer.neighborhood, property_type=offer.property_type,
                    offer_type=offer.listing_type, category=offer.category,
                    video_url=offer.video_link,
                    video_enabled=getattr(offer, "video_enabled", True),
                    map_url=offer.google_map,
                    owner_notes=offer.owner_notes, area=area_val, price=price_val,
                    property_age=offer.property_age, floors=offer.floors, rooms=offer.rooms,
                    apartments=offer.apartments, bathrooms=offer.bathrooms,
                    show_price_to_visitors=True
                )
                
                imgs = sorted(list(offer.images.all()), key=lambda x: (0 if getattr(x, "is_cover", False) else 1, getattr(x, "sort_order", 0), x.id))
                for i, img_obj in enumerate(imgs[:10], start=1):
                    if getattr(img_obj, "image", None):
                        setattr(prop, f"image{i}", img_obj.image)
                prop.save()

                # تصدير إلى قوقل شيت تلقائياً عند النشر
                sync_published_property_async(prop.pk)

                offer.status = PropertyOffer.Status.PUBLISHED
                offer.save()
                published += 1

        if published: self.message_user(request, f"تم تحويل {published} طلب إلى عقارات.", messages.SUCCESS)
        if skipped: self.message_user(request, f"تم تخطي {skipped} طلبات (منشورة مسبقاً أو بيانات خاطئة).", messages.WARNING)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if staff_is_co_admin(request.user):
            return qs
        if request.user.is_staff:
            return qs.filter(assigned_to=request.user)
        return qs

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if staff_is_co_admin(request.user):
            return request.user.is_staff
        if not request.user.is_staff:
            return super().has_view_permission(request, obj)
        if obj is None:
            return True
        if obj.assigned_to_id == request.user.id:
            return True
        return False

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if staff_is_co_admin(request.user):
            return request.user.is_staff
        if not request.user.is_staff:
            return super().has_change_permission(request, obj)
        if obj is None:
            return True
        if obj.assigned_to_id == request.user.id:
            return True
        return False

    def has_add_permission(self, request):
        if staff_is_co_admin(request.user):
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        if staff_is_co_admin(request.user):
            return False
        return super().has_delete_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser or not staff_is_co_admin(request.user):
            return super().get_readonly_fields(request, obj)
        all_fields = [f.name for f in self.model._meta.fields]
        allowed = {"assigned_to"}
        readonly = [f for f in all_fields if f not in allowed]
        for rf in super().get_readonly_fields(request, obj):
            if rf not in readonly:
                readonly.append(rf)
        return readonly

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not staff_is_co_admin(request.user):
            return actions
        return {
            name: val
            for name, val in actions.items()
            if name in self.co_admin_assignment_actions
        }

    def has_module_permission(self, request):
        """يظهر النموذج في Jazzmin/فهرس الأدمن للموظفين دون صلاحيات Django الافتراضية؛ التصفية من get_queryset."""
        return request.user.is_active and request.user.is_staff


# -----------------------------------------------------
# واجهة إدارة العملاء (PropertyLead)
# -----------------------------------------------------
@admin.register(PropertyLead)
class PropertyLeadAdmin(admin.ModelAdmin):
    list_display = ('name', 'status_badge', 'phone', 'property', 'assigned_to', 'source', 'created_at')
    list_filter = ('status', 'assigned_to', 'source', 'created_at')
    readonly_fields = ('created_at', 'ip_address', 'smart_link')
    actions = [
        "ai_reply_to_lead", 
        "assign_to_me", 
        "assign_to_marketer",
        "mark_as_interested",
        "mark_as_not_interested",
        "mark_as_neutral",
        "mark_as_special",
        "export_to_sheets_action"
    ]
    co_admin_assignment_actions = ("assign_to_marketer", "assign_to_me")

    @admin.action(description="📤 تصدير إلى قوقل شيت")
    def export_to_sheets_action(self, request, queryset):
        count = queryset.count()
        for lead in queryset:
            sync_property_lead_async(lead.pk)
        self.message_user(request, f"جاري تصدير {count} عميل مهتم إلى قوقل شيت...", messages.SUCCESS)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if staff_is_co_admin(request.user):
            return qs
        return qs.filter(smart_link__marketer=request.user)

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if staff_is_co_admin(request.user):
            return request.user.is_staff
        if not request.user.is_staff:
            return False
        if obj is None:
            return True
        if obj.smart_link_id and obj.smart_link.marketer_id == request.user.id:
            return True
        if obj.assigned_to_id == request.user.id:
            return True
        return False

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if staff_is_co_admin(request.user):
            return request.user.is_staff
        if not request.user.is_staff:
            return False
        if obj is None:
            return True
        if obj.smart_link_id and obj.smart_link.marketer_id == request.user.id:
            return True
        if obj.assigned_to_id == request.user.id:
            return True
        return False

    def has_add_permission(self, request):
        if staff_is_co_admin(request.user):
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        if staff_is_co_admin(request.user):
            return False
        return super().has_delete_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser or not staff_is_co_admin(request.user):
            return super().get_readonly_fields(request, obj)
        all_fields = [f.name for f in self.model._meta.fields]
        allowed = {"assigned_to"}
        readonly = [f for f in all_fields if f not in allowed]
        for rf in super().get_readonly_fields(request, obj):
            if rf not in readonly:
                readonly.append(rf)
        return readonly

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not staff_is_co_admin(request.user):
            return actions
        return {
            name: val
            for name, val in actions.items()
            if name in self.co_admin_assignment_actions
        }

    def has_module_permission(self, request):
        """يظهر النموذج في Jazzmin/فهرس الأدمن للموظفين دون صلاحيات Django الافتراضية؛ التصفية من get_queryset."""
        return request.user.is_active and request.user.is_staff

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        from django.contrib.auth.models import User
        from django.contrib.humanize.templatetags.humanize import intcomma
        from django.urls import reverse
        from django.utils import timezone
        from listings.services.dashboard_service import DashboardService

        # Marketers list for assignment dropdown
        raw_marketers = User.objects.filter(is_staff=True).only("id", "first_name", "last_name", "username")
        marketers_data = []
        for m in raw_marketers:
            name = m.get_full_name() or m.username
            marketers_data.append({
                'id': m.id,
                'name': name,
                'initial': (name[0].upper() if name else "?") if name else "?"
            })
        extra_context['marketers'] = marketers_data
        extra_context['header_stats'] = DashboardService.get_lead_header_stats()

        cl = self.get_changelist_instance(request)
        results = []
        for obj in cl.result_list:
            results.append({
                'id': obj.id,
                'name': obj.name,
                'phone': obj.phone,
                'property': str(obj.property) if obj.property else "—",
                'source': obj.source,
                'status_html': self.status_badge(obj),
                'assigned_to': (obj.assigned_to.get_full_name() or obj.assigned_to.username) if obj.assigned_to else "غير مسند",
                'is_new': obj.created_at.date() == timezone.now().date(),
                'edit_url': reverse('admin:listings_propertylead_change', args=[obj.pk])
            })
        extra_context['results'] = results

        # قمع المبيعات (Kanban) — نفس نطاق صلاحيات القائمة (عملاء محتملون حقيقيون)
        pipeline_max_per_column = 60
        pipeline_qs = (
            self.get_queryset(request)
            .select_related("property", "assigned_to")
            .order_by("-created_at")
        )
        extra_context["pipeline_total"] = pipeline_qs.count()
        buckets = {
            "new": [],
            "interested": [],
            "special_request": [],
            "followup": [],
        }
        sub_status_labels = {
            "neutral": "محايد",
            "not_interested": "غير مهتم",
        }

        for lead in pipeline_qs:
            if lead.status == PropertyLead.Status.NEW:
                key = "new"
            elif lead.status == PropertyLead.Status.INTERESTED:
                key = "interested"
            elif lead.status == PropertyLead.Status.SPECIAL_REQUEST:
                key = "special_request"
            elif lead.status in (PropertyLead.Status.NEUTRAL, PropertyLead.Status.NOT_INTERESTED):
                key = "followup"
            else:
                key = "new"
            if len(buckets[key]) >= pipeline_max_per_column:
                continue

            prop = lead.property
            price_val = None
            if prop is not None and prop.price is not None:
                price_val = intcomma(prop.price)

            if prop and prop.district:
                property_line = f"{prop.property_type} في {prop.district}"
            elif prop:
                property_line = str(prop)
            else:
                property_line = "—"

            buckets[key].append({
                "id": lead.id,
                "name": lead.name or "—",
                "phone": lead.phone or "",
                "property_line": property_line,
                "date": lead.created_at,
                "edit_url": reverse("admin:listings_propertylead_change", args=[lead.pk]),
                "price": price_val,
                "sub_status": sub_status_labels.get(lead.status, "") if key == "followup" else "",
            })

        pipeline_columns = [
            {
                "key": "new",
                "label_ar": "جديد",
                "label_en": "New",
                "items": buckets["new"],
                "count": len(buckets["new"]),
            },
            {
                "key": "interested",
                "label_ar": "مهتم",
                "label_en": "Interested",
                "items": buckets["interested"],
                "count": len(buckets["interested"]),
            },
            {
                "key": "special_request",
                "label_ar": "طلب خاص",
                "label_en": "Special",
                "items": buckets["special_request"],
                "count": len(buckets["special_request"]),
            },
            {
                "key": "followup",
                "label_ar": "محايد / غير مهتم",
                "label_en": "Neutral / Not interested",
                "items": buckets["followup"],
                "count": len(buckets["followup"]),
            },
        ]
        extra_context["pipeline_columns"] = pipeline_columns

        return super().changelist_view(request, extra_context=extra_context)

    @admin.display(description="الحالة")
    def status_badge(self, obj):
        colors = {
            'new': ('rgba(212, 175, 55, 0.1)', '#D4AF37', 'جديد'),
            'interested': ('rgba(34, 197, 94, 0.1)', '#22C55E', 'عميل مهتم'),
            'not_interested': ('rgba(239, 68, 68, 0.1)', '#EF4444', 'غير مهتم'),
            'neutral': ('rgba(100, 116, 139, 0.1)', '#64748B', 'عميل محايد'),
            'special_request': ('rgba(139, 92, 246, 0.1)', '#8B5CF6', 'طلب خاص'),
        }
        bg, text, label = colors.get(obj.status, ('rgba(100, 116, 139, 0.1)', '#64748B', obj.status))
        style = f"display: inline-block; padding: 4px 12px; border-radius: 6px; font-weight: 700; font-size: 0.75rem; background-color: {bg}; color: {text};"
        return format_html('<span style="{}">{}</span>', style, label)

    @admin.action(description="👤 إسناد للعملاء لمسوق معين")
    def assign_to_marketer(self, request, queryset):
        marketer_id = request.POST.get('marketer_id')
        if not marketer_id:
            self.message_user(request, "يرجى اختيار مسوق من القائمة المنسدلة.", messages.WARNING)
            return
        from django.contrib.auth.models import User
        try:
            marketer = User.objects.get(id=marketer_id)
            updated = queryset.update(assigned_to=marketer)
            self.message_user(request, f"تم إسناد {updated} عملاء إلى {marketer.get_full_name() or marketer.username}.", messages.SUCCESS)
        except User.DoesNotExist:
            self.message_user(request, "المسوق غير موجود.", messages.ERROR)

    @admin.action(description="🙋 إسناد لي (أنا)")
    def assign_to_me(self, request, queryset):
        updated = queryset.update(assigned_to=request.user)
        self.message_user(request, f"تم إسناد {updated} عملاء إليك.", messages.SUCCESS)

    @admin.action(description="✅ تحديد كـ 'مهتم'")
    def mark_as_interested(self, request, queryset):
        updated = queryset.update(status='interested')
        self.message_user(request, f"تم تحديث {updated} عملاء إلى 'مهتم'.", messages.SUCCESS)

    @admin.action(description="❌ تحديد كـ 'غير مهتم'")
    def mark_as_not_interested(self, request, queryset):
        updated = queryset.update(status='not_interested')
        self.message_user(request, f"تم تحديث {updated} عملاء إلى 'غير مهتم'.", messages.SUCCESS)

    @admin.action(description="😐 تحديد كـ 'محايد'")
    def mark_as_neutral(self, request, queryset):
        updated = queryset.update(status='neutral')
        self.message_user(request, f"تم تحديث {updated} عملاء إلى 'محايد'.", messages.SUCCESS)

    @admin.action(description="⭐ تحديد كـ 'طلب خاص'")
    def mark_as_special(self, request, queryset):
        updated = queryset.update(status='special_request')
        self.message_user(request, f"تم تحديث {updated} عملاء إلى 'طلب خاص'.", messages.SUCCESS)

    @admin.action(description="✨ توليد رد ذكي (AI) للعميل")
    def ai_reply_to_lead(self, request, queryset):
        from .services.ai_utils import generate_reply_to_inquiry
        from django.http import HttpResponse
        from urllib.parse import quote
        
        if queryset.count() > 1:
            self.message_user(request, "يرجى اختيار عميل واحد فقط للرد عليه.", messages.WARNING)
            return
            
        lead = queryset.first()
        prop_title = lead.property.full_name if lead.property else "عقارنا"
        inquiry = lead.message or "استفسار عن العقار"
        
        success, reply_text = generate_reply_to_inquiry(prop_title, inquiry)
        
        if success:
            base_url = request.build_absolute_uri("/admin/listings/propertylead/")
            wa_url = f"https://wa.me/{lead.phone}?text={quote(reply_text)}"
            
            html = f"""
            <!DOCTYPE html>
            <html dir="rtl" lang="ar">
            <head>
                <meta charset="utf-8">
                <title>رد ذكي على العميل</title>
                <style>
                    body {{ font-family: Tahoma, Arial, sans-serif; background: #f0f4f8; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }}
                    .box {{ background: white; padding: 40px; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); width: 100%; max-width: 600px; text-align: center; }}
                    h2 {{ color: #0B1B3A; margin-bottom: 20px; }}
                    p {{ color: #666; margin-bottom: 20px; }}
                    .reply-box {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 10px; padding: 20px; text-align: right; margin-bottom: 25px; white-space: pre-wrap; font-size: 16px; line-height: 1.8; color: #374151; }}
                    .btn {{ display: inline-block; padding: 14px 30px; background: #25D366; color: white; text-decoration: none; border-radius: 50px; font-weight: bold; font-size: 16px; transition: 0.3s; margin: 5px; border: none; cursor: pointer; }}
                    .btn:hover {{ background: #1ebd5c; transform: translateY(-2px); }}
                    .btn-secondary {{ background: #6b7280; }}
                    .btn-secondary:hover {{ background: #4b5563; }}
                </style>
            </head>
            <body>
                <div class="box">
                    <h2>✨ الرد المقترح من الذكاء الاصطناعي</h2>
                    <p>العميل: <strong>{lead.name}</strong> | العقار: <strong>{prop_title}</strong></p>
                    <div class="reply-box" id="replyText">{reply_text}</div>
                    <a href="{wa_url}" target="_blank" class="btn">📲 إرسال عبر واتساب</a>
                    <button onclick="navigator.clipboard.writeText(document.getElementById('replyText').innerText); alert('تم نسخ الرد!')" class="btn btn-secondary">📋 نسخ الرد</button>
                    <br><br>
                    <a href="{base_url}" style="color: #6b7280; text-decoration: none;">← العودة للوحة التحكم</a>
                </div>
            </body>
            </html>
            """
            return HttpResponse(html)
        else:
            self.message_user(request, reply_text, messages.ERROR)

# -----------------------------------------------------
# واجهة إدارة الروابط الذكية (PropertySmartLink)
# -----------------------------------------------------
@admin.register(PropertySmartLink)
class PropertySmartLinkAdmin(admin.ModelAdmin):
    list_display = ('property', 'marketer', 'token', 'smart_url_link', 'views', 'inquiry_count', 'created_at')
    list_filter = ('marketer', 'created_at')
    search_fields = ('property__listing_id', 'token', 'marketer__username')
    readonly_fields = ('token', 'views', 'inquiry_count', 'created_at')
    ordering = ('-created_at',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(marketer=request.user)

    def get_list_display(self, request):
        if request.user.is_superuser:
            return self.list_display
        # المسوّق يرى روابطه فقط؛ عمود «المسوق» زائد
        return ('property', 'token', 'smart_url_link', 'views', 'inquiry_count', 'created_at')

    def get_list_filter(self, request):
        if request.user.is_superuser:
            return self.list_filter
        return ('created_at',)

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return super().has_view_permission(request, obj)
        if obj is not None and obj.marketer_id != request.user.id:
            return False
        if request.user.is_staff:
            return True
        return super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return super().has_change_permission(request, obj)
        if obj is not None and obj.marketer_id != request.user.id:
            return False
        if request.user.is_staff:
            return True
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return super().has_delete_permission(request, obj)
        if obj is not None and obj.marketer_id != request.user.id:
            return False
        return super().has_delete_permission(request, obj)

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff

    @admin.display(description="الرابط المباشر")
    def smart_url_link(self, obj):
        url = reverse('listings:smart-brochure', kwargs={'token': obj.token})
        base = getattr(settings, "PUBLIC_SITE_URL", "https://jodah.onrender.com").rstrip("/")
        full_url = f"{base}{url}"
        return format_html('<a href="{}" target="_blank" style="color:#C9A24A; font-weight:bold;">فتح الرابط 🔗</a>', full_url)

    def get_exclude(self, request, obj=None):
        ex = list(super().get_exclude(request, obj) or [])
        # المسوّق لا يختار مستخدماً آخر؛ يُثبَّت تلقائياً على الحساب الحالي
        if not request.user.is_superuser and 'marketer' not in ex:
            ex.append('marketer')
        return tuple(ex) if ex else None

    def get_readonly_fields(self, request, obj=None):
        if obj:
            if request.user.is_superuser:
                return self.readonly_fields + ('property', 'marketer')
            return self.readonly_fields + ('property',)
        return self.readonly_fields

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'property' and not request.user.is_superuser:
            kwargs['queryset'] = Property.objects.filter(visibility='منشور').order_by('-created_at')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        # يمنع تعيين مسوّق آخر عبر POST حتى لو تلاعب بالنموذج
        if not request.user.is_superuser:
            obj.marketer = request.user
        super().save_model(request, obj, form, change)


@admin.register(SmartLinkViewLog)
class SmartLinkViewLogAdmin(admin.ModelAdmin):
    list_display = ('smart_link', 'ip_address', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('smart_link__token', 'ip_address', 'user_agent')
    readonly_fields = ('smart_link', 'ip_address', 'user_agent', 'created_at')
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


# -----------------------------------------------------
# واجهة إدارة الطلبات السريعة (FastRequest)
# -----------------------------------------------------
@admin.register(FastRequest)
class FastRequestAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'assigned_to', 'smart_link', 'is_read', 'created_at')
    list_filter = ('is_read', 'assigned_to', 'created_at')
    search_fields = ('name', 'phone', 'request_text')
    readonly_fields = ('created_at', 'smart_link')
    ordering = ('-created_at',)
    actions_on_top = False
    actions_on_bottom = False
    actions = [
        'mark_as_read',
        'mark_as_unread',
        'assign_to_me',
        'assign_to_marketer',
        'ai_reply_to_fast_request',
        'delete_selected',
    ]

    def get_queryset(self, request):
        from django.db.models import Q

        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(
            Q(smart_link__marketer=request.user) | Q(assigned_to=request.user)
        )

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if not request.user.is_staff:
            return super().has_view_permission(request, obj)
        if obj is None:
            return True
        if obj.smart_link and obj.smart_link.marketer_id == request.user.id:
            return True
        if obj.assigned_to_id == request.user.id:
            return True
        return False

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if not request.user.is_staff:
            return super().has_change_permission(request, obj)
        if obj is None:
            return True
        if obj.smart_link and obj.smart_link.marketer_id == request.user.id:
            return True
        if obj.assigned_to_id == request.user.id:
            return True
        return False

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        qs = self.get_queryset(request)
        extra_context['header_stats'] = {
            'total': qs.count(),
            'unread': qs.filter(is_read=False).count(),
        }
        raw_marketers = User.objects.filter(is_staff=True).only("id", "first_name", "last_name", "username")
        marketers_data = []
        for m in raw_marketers:
            name = m.get_full_name() or m.username
            marketers_data.append({
                'id': m.id,
                'name': name,
                'initial': (name[0].upper() if name else "?") if name else "?",
            })
        extra_context['marketers'] = marketers_data
        return super().changelist_view(request, extra_context=extra_context)

    @admin.action(description="👤 إسناد الطلبات لمسوق معين")
    def assign_to_marketer(self, request, queryset):
        marketer_id = request.POST.get('marketer_id')
        if not marketer_id:
            self.message_user(request, "يرجى اختيار مسوق من القائمة.", messages.WARNING)
            return
        try:
            marketer = User.objects.get(id=marketer_id)
            updated = queryset.update(assigned_to=marketer)
            self.message_user(
                request,
                f"تم إسناد {updated} طلبات إلى {marketer.get_full_name() or marketer.username} بنجاح.",
                messages.SUCCESS,
            )
        except User.DoesNotExist:
            self.message_user(request, "المسوق المختار غير موجود.", messages.ERROR)

    @admin.action(description="🙋 إسناد لي (أنا)")
    def assign_to_me(self, request, queryset):
        updated = queryset.update(assigned_to=request.user)
        self.message_user(request, f"تم إسناد {updated} طلبات إليك بنجاح.", messages.SUCCESS)

    @admin.action(description="تحديد كمقروء")
    def mark_as_read(self, request, queryset):
        updated = queryset.update(is_read=True)
        self.message_user(request, f"تم تحديد {updated} طلب كمقروء.", messages.SUCCESS)

    @admin.action(description="تحديد كغير مقروء")
    def mark_as_unread(self, request, queryset):
        updated = queryset.update(is_read=False)
        self.message_user(request, f"تم تحديد {updated} طلب كغير مقروء.", messages.SUCCESS)

    @admin.action(description="✨ توليد رد ذكي (AI) للعميل")
    def ai_reply_to_fast_request(self, request, queryset):
        from .services.ai_utils import generate_reply_to_inquiry
        from django.http import HttpResponse
        from urllib.parse import quote
        
        if queryset.count() > 1:
            self.message_user(request, "يرجى اختيار طلب واحد فقط للرد عليه.", messages.WARNING)
            return
            
        req = queryset.first()
        prop_title = req.smart_link.property.full_name if (req.smart_link and req.smart_link.property) else "عقارنا"
        inquiry = req.request_text or "استفسار عن العقار"
        
        success, reply_text = generate_reply_to_inquiry(prop_title, inquiry)
        
        if success:
            base_url = request.build_absolute_uri("/admin/listings/fastrequest/")
            wa_url = f"https://wa.me/{req.phone}?text={quote(reply_text)}"
            
            html = f"""
            <!DOCTYPE html>
            <html dir="rtl" lang="ar">
            <head>
                <meta charset="utf-8">
                <title>رد ذكي على طلب سريع</title>
                <style>
                    body {{ font-family: Tahoma, Arial, sans-serif; background: #f0f4f8; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }}
                    .box {{ background: white; padding: 40px; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); width: 100%; max-width: 600px; text-align: center; }}
                    h2 {{ color: #0B1B3A; margin-bottom: 20px; }}
                    p {{ color: #666; margin-bottom: 20px; }}
                    .reply-box {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 10px; padding: 20px; text-align: right; margin-bottom: 25px; white-space: pre-wrap; font-size: 16px; line-height: 1.8; color: #374151; }}
                    .btn {{ display: inline-block; padding: 14px 30px; background: #25D366; color: white; text-decoration: none; border-radius: 50px; font-weight: bold; font-size: 16px; transition: 0.3s; margin: 5px; border: none; cursor: pointer; }}
                    .btn:hover {{ background: #1ebd5c; transform: translateY(-2px); }}
                    .btn-secondary {{ background: #6b7280; }}
                    .btn-secondary:hover {{ background: #4b5563; }}
                </style>
            </head>
            <body>
                <div class="box">
                    <h2>✨ الرد المقترح من الذكاء الاصطناعي</h2>
                    <p>العميل: <strong>{req.name}</strong> | العقار: <strong>{prop_title}</strong></p>
                    <div class="reply-box" id="replyText">{reply_text}</div>
                    <a href="{wa_url}" target="_blank" class="btn">📲 إرسال عبر واتساب</a>
                    <button onclick="navigator.clipboard.writeText(document.getElementById('replyText').innerText); alert('تم نسخ الرد!')" class="btn btn-secondary">📋 نسخ الرد</button>
                    <br><br>
                    <a href="{base_url}" style="color: #6b7280; text-decoration: none;">← العودة للوحة التحكم</a>
                </div>
            </body>
            </html>
            """
            return HttpResponse(html)
        else:
            self.message_user(request, reply_text, messages.ERROR)


# ─────────────────────────────────────────────────────────────
# Inline للمطابقات داخل صفحة الطلب
# ─────────────────────────────────────────────────────────────
class PropertyMatchInline(admin.TabularInline):
    model = PropertyMatch
    extra = 0
    readonly_fields = ("property_link", "score_badge", "created_at")
    fields = ("property_link", "score_badge", "created_at")
    can_delete = False
    verbose_name = "مطابقة"
    verbose_name_plural = "العقارات المطابقة"

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="العقار")
    def property_link(self, obj):
        if not obj.property:
            return "—"
        url = reverse("admin:listings_property_change", args=[obj.property.pk])
        return format_html(
            '<a href="{}" target="_blank"><strong>{}</strong> – {} – {} ريال</a>',
            url, obj.property.listing_id or "—",
            obj.property.property_type, f"{float(obj.property.price):,.0f}",
        )

    @admin.display(description="نسبة المطابقة")
    def score_badge(self, obj):
        pct = f"{obj.score * 100:.0f}"
        color = "#22C55E" if obj.score >= 0.8 else "#F59E0B" if obj.score >= 0.6 else "#9CA3AF"
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 10px;border-radius:12px;font-weight:700;">{}%</span>',
            color, pct,
        )


# -----------------------------------------------------
# واجهة إدارة طلبات الحجز والمعاينة (PropertyBooking)
# -----------------------------------------------------
@admin.register(PropertyBooking)
class PropertyBookingAdmin(admin.ModelAdmin):
    list_display = ('property_link', 'name', 'phone', 'booking_date', 'booking_time_12h', 'created_at')
    list_filter = ('booking_date', 'created_at')
    search_fields = ('name', 'phone', 'property__listing_id')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

    @admin.display(description="العقار")
    def property_link(self, obj):
        url = reverse("admin:listings_property_change", args=[obj.property.pk])
        return format_html('<a href="{}" target="_blank">{}</a>', url, obj.property.listing_id or "—")

    @admin.display(description="وقت المعاينة")
    def booking_time_12h(self, obj):
        if not obj.booking_time:
            return "—"
        # تحويل الوقت لنظام 12 ساعة مع تسمية عربية
        return obj.booking_time.strftime("%I:%M %p").replace("AM", "صباحاً").replace("PM", "مساءً")


# -----------------------------------------------------
# واجهة إدارة مواعيد المعاينة (Appointment)
# -----------------------------------------------------
@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("property_link", "client_name", "client_phone", "booking_date", "booking_time_12h", "status_badge", "created_at")
    list_filter = ("status", "booking_date", "created_at")
    search_fields = ("client_name", "client_phone", "client_email", "property__listing_id")
    readonly_fields = ("cancel_token", "created_at", "updated_at")
    ordering = ("-created_at",)

    @admin.display(description="العقار")
    def property_link(self, obj):
        url = reverse("admin:listings_property_change", args=[obj.property.pk])
        return format_html('<a href="{}" target="_blank">{}</a>', url, obj.property.listing_id or "—")

    @admin.display(description="وقت الموعد")
    def booking_time_12h(self, obj):
        if not obj.booking_time:
            return "—"
        return obj.booking_time.strftime("%I:%M %p").replace("AM", "صباحاً").replace("PM", "مساءً")

    @admin.display(description="الحالة")
    def status_badge(self, obj):
        colors = {
            Appointment.Status.PENDING: ("#f59e0b", "قيد المراجعة"),
            Appointment.Status.CONFIRMED: ("#22c55e", "مؤكد"),
            Appointment.Status.CANCELED: ("#ef4444", "ملغي"),
        }
        bg, label = colors.get(obj.status, ("#64748b", obj.get_status_display()))
        return format_html(
            '<span style="background:{};color:#fff;padding:4px 10px;border-radius:999px;font-size:0.78rem;font-weight:700;">{}</span>',
            bg, label
        )


# ─────────────────────────────────────────────────────────────
# واجهة إدارة طلبات العقارات (PropertyRequest)
# ─────────────────────────────────────────────────────────────
@admin.register(PropertyRequest)
class PropertyRequestAdmin(admin.ModelAdmin):
    inlines = [PropertyMatchInline]
    list_display = (
        "id",
        "name",
        "phone_wa_link",
        "property_type",
        "district",
        "budget_display",
        "source_badge",
        "lead_score_display",
        "priority_badge",
        "created_at",
    )
    list_filter = ("source", "property_type", "district")
    search_fields = ("name", "phone")
    readonly_fields = ("match_score", "matched_count", "score", "priority", "created_at", "updated_at")
    ordering = ("-created_at",)
    list_per_page = 30
    date_hierarchy = "created_at"
    fieldsets = (
        ("بيانات العميل", {"fields": ("name", "phone", "source", "conversation_id")}),
        (
            "تفاصيل الطلب",
            {
                "fields": (
                    "property_type",
                    "request_type",
                    "usage_type",
                    "city",
                    "district",
                    "budget",
                    "category",
                    "rooms",
                    "furnished",
                ),
            },
        ),
        ("المواصفات الفنية", {
            "fields": (
                "property_age", "area", "floors_count", 
                "apartments_count", "rooms_count", "bathrooms_count"
            ),
            "description": "المواصفات الفنية المطلوبة للعقار (حقول نصية قديمة و/أو من النماذج الطويلة)"
        }),
        ("ملاحظات العميل", {"fields": ("notes",)}),
        ("Lead scoring", {"fields": ("score", "priority"), "classes": ("collapse",)}),
        ("الحالة والإسناد", {"fields": ("status", "client_segment", "assigned_to")}),
        ("نتائج المطابقة", {"fields": ("match_score", "matched_count"), "classes": ("collapse",)}),
        ("التواريخ", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
    actions = [
        "generate_whatsapp_message",
        "run_matching_engine",
        "mark_as_contacted",
        "segment_mark_interested",
        "segment_mark_potential",
        "segment_mark_special",
        "segment_reset_search",
        "assign_to_marketer",
        "assign_to_me",
        "delete_selected",
    ]
    co_admin_assignment_actions = ("assign_to_marketer", "assign_to_me")

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if staff_is_co_admin(request.user):
            return request.user.is_staff
        if not request.user.is_staff:
            return super().has_view_permission(request, obj)
        if obj is None:
            return True
        if obj.assigned_to_id == request.user.id:
            return True
        return super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if staff_is_co_admin(request.user):
            return request.user.is_staff
        if not request.user.is_staff:
            return super().has_change_permission(request, obj)
        if obj is None:
            return True
        if obj.assigned_to_id == request.user.id:
            return True
        return super().has_change_permission(request, obj)

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if staff_is_co_admin(request.user):
            return qs
        return qs.filter(assigned_to=request.user)

    def has_add_permission(self, request):
        if staff_is_co_admin(request.user):
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        if staff_is_co_admin(request.user):
            return False
        return super().has_delete_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            return self.readonly_fields
        if staff_is_co_admin(request.user):
            all_fields = [f.name for f in self.model._meta.fields]
            allowed = {"assigned_to"}
            readonly = [f for f in all_fields if f not in allowed]
            for rf in self.readonly_fields:
                if rf not in readonly:
                    readonly.append(rf)
            return readonly
        
        # For marketers: restrict everything except status and notes
        all_fields = [f.name for f in self.model._meta.fields]
        allowed = ['status', 'notes', 'client_segment']
        readonly = [f for f in all_fields if f not in allowed]
        
        # Merge with existing readonly_fields
        for rf in self.readonly_fields:
            if rf not in readonly:
                readonly.append(rf)
        return readonly

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not staff_is_co_admin(request.user):
            return actions
        return {
            name: val
            for name, val in actions.items()
            if name in self.co_admin_assignment_actions
        }

    @admin.display(description="الجوال")
    def phone_wa_link(self, obj):
        return format_html('<a href="https://wa.me/{}" target="_blank">📱 {}</a>', obj.phone, obj.phone)

    @admin.display(description="الميزانية")
    def budget_display(self, obj):
        return f"{float(obj.budget):,.0f} ريال" if obj.budget else "—"

    @admin.display(description="Lead score")
    def lead_score_display(self, obj):
        if obj.score is None:
            return "—"
        return f"{float(obj.score):.1f}"

    @admin.display(description="الأولوية")
    def priority_badge(self, obj):
        colors = {
            "high": ("#b91c1c", "High"),
            "medium": ("#ca8a04", "Medium"),
            "low": ("#64748b", "Low"),
        }
        bg, label = colors.get(obj.priority, ("#94a3b8", obj.priority or "—"))
        return format_html(
            '<span style="background:{};color:#fff;padding:4px 10px;border-radius:8px;font-size:0.78rem;font-weight:600;">{}</span>',
            bg,
            label,
        )

    @admin.display(description="المصدر")
    def source_badge(self, obj):
        # Website / AI Chat per spec؛ باقي المصادر بألوان واضحة للفريق
        colors = {
            "website": ("#16a34a", "الموقع"),
            "ai_chat": ("#2563eb", "المساعد الذكي"),
            "whatsapp": ("#128C7E", "واتساب"),
            "manual": ("#64748b", "يدوي"),
        }
        bg, label = colors.get(obj.source, ("#94a3b8", obj.get_source_display()))
        return format_html(
            '<span style="background:{};color:#fff;padding:5px 12px;border-radius:10px;'
            'font-weight:600;font-size:0.8rem;display:inline-block;text-align:center;min-width:72px;">{}</span>',
            bg,
            label,
        )

    @admin.display(description="الحالة")
    def status_badge(self, obj):
        # Update colors and labels for the new statuses
        colors = {
            "new": ("#3B82F6", "جديد - غير معالج"), 
            "working": ("#F59E0B", "قيد العمل / في المهام"),
            "contacted": ("#8B5CF6", "تم التواصل مع العميل"), 
            "matched": ("#22C55E", "تمت المطابقة"),
            "closed": ("#10B981", "مغلق - تم الإنجاز"), 
            "lost": ("#EF4444", "مفقود / غير جاد"),
        }
        bg, label = colors.get(obj.status, ("#9CA3AF", obj.status))
        return format_html(
            '<span style="background:{};color:#fff;padding:6px 14px;border-radius:12px;font-weight:700;font-size:0.85rem;display:inline-block;min-width:100px;text-align:center;">{}</span>',
            bg, label,
        )

    @admin.display(description="تصنيف العميل")
    def client_segment_badge(self, obj):
        colors = {
            "search": ("rgba(148, 163, 184, 0.25)", "#E2E8F0", "طلب بحث — عادي"),
            "potential": ("rgba(245, 158, 11, 0.2)", "#FBBF24", "عميل محتمل"),
            "interested": ("rgba(34, 197, 94, 0.2)", "#4ADE80", "مهتم"),
            "special": ("rgba(139, 92, 246, 0.25)", "#C4B5FD", "طلب خاص"),
        }
        bg, fg, label = colors.get(obj.client_segment, ("#374151", "#fff", obj.client_segment))
        return format_html(
            '<span style="background:{};color:{};padding:5px 12px;border-radius:10px;font-weight:700;font-size:0.8rem;display:inline-block;min-width:88px;text-align:center;border:1px solid rgba(255,255,255,0.08);">{}</span>',
            bg, fg, label,
        )

    @admin.display(description="نسبة المطابقة")
    def match_score_colored(self, obj):
        pct = f"{obj.match_score * 100:.0f}"
        bg = "#22C55E" if obj.match_score >= 0.8 else "#F59E0B" if obj.match_score >= 0.6 else "#9CA3AF"
        return format_html(
            '<span style="background:{};color:#fff;padding:4px 12px;border-radius:12px;font-weight:700;">{}%</span>',
            bg, pct,
        )

    @admin.action(description="👤 إسناد الطلبات لمسوق معين")
    def assign_to_marketer(self, request, queryset):
        marketer_id = request.POST.get('marketer_id')
        if not marketer_id:
            self.message_user(request, "يرجى اختيار مسوق من القائمة المنسدلة.", messages.WARNING)
            return
        
        from django.contrib.auth.models import User
        try:
            marketer = User.objects.get(id=marketer_id)
            updated = queryset.update(assigned_to=marketer)
            self.message_user(request, f"تم إسناد {updated} طلبات إلى {marketer.get_full_name() or marketer.username} بنجاح.", messages.SUCCESS)
        except User.DoesNotExist:
            self.message_user(request, "المسوق المختار غير موجود.", messages.ERROR)

    @admin.action(description="🙋 إسناد الطلبات لي (أنا)")
    def assign_to_me(self, request, queryset):
        updated = queryset.update(assigned_to=request.user)
        self.message_user(request, f"تم إسناد {updated} طلبات إليك بنجاح.", messages.SUCCESS)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        from django.contrib.auth.models import User
        from listings.services.dashboard_service import DashboardService
        
        raw_marketers = User.objects.filter(is_staff=True).only("id", "first_name", "last_name", "username")
        marketers_data = []
        for m in raw_marketers:
            name = m.get_full_name() or m.username
            marketers_data.append({
                'id': m.id,
                'name': name,
                'initial': name[0].upper() if name else "?"
            })
        extra_context['marketers'] = marketers_data
        extra_context['header_stats'] = DashboardService.get_request_header_stats()
        
        cl = self.get_changelist_instance(request)
        results = []
        for obj in cl.result_list:
            results.append({
                'id': obj.id,
                'name': obj.name,
                'phone': obj.phone,
                'property_type': obj.property_type,
                'district': obj.district,
                'budget': f"{float(obj.budget):,.0f}" if obj.budget else "—",
                'date': obj.created_at.strftime('%Y-%m-%d'),
                'status_html': self.status_badge(obj),
                'segment_html': self.client_segment_badge(obj),
                'assigned_to': (obj.assigned_to.get_full_name() or obj.assigned_to.username) if obj.assigned_to else "غير مسند",
                'is_new': obj.created_at.date() == timezone.now().date(),
                'edit_url': reverse('admin:listings_propertyrequest_change', args=[obj.pk])
            })
        extra_context['results'] = results
        return super().changelist_view(request, extra_context=extra_context)

    @admin.action(description="⚡ تشغيل محرك المطابقة")
    def run_matching_engine(self, request, queryset):
        from .services.matching import PropertyMatcher
        matcher = PropertyMatcher()
        total = 0
        for req in queryset:
            try:
                total += len(matcher.match_request(req))
            except Exception as e:
                self.message_user(request, f"خطأ في الطلب #{req.id}: {e}", messages.ERROR)
        self.message_user(request, f"✅ تم تشغيل المطابقة على {queryset.count()} طلب، المطابقات: {total}.", messages.SUCCESS)

    @admin.action(description="💬 توليد رسالة واتساب للمطابقات")
    def generate_whatsapp_message(self, admin_request, queryset):
        from urllib.parse import quote
        if queryset.count() > 1:
            self.message_user(admin_request, "⚠️ اختر طلباً واحداً فقط.", messages.WARNING)
            return
        req = queryset.select_related("assigned_to").first()
        matches = req.matches.select_related("property").order_by("-score")[:10]
        if not matches:
            self.message_user(admin_request, "⚠️ لا توجد عقارات مطابقة. شغّل محرك المطابقة أولاً.", messages.WARNING)
            return
        base_url = admin_request.build_absolute_uri("/").rstrip("/")
        prop_lines = []
        for i, match in enumerate(matches, 1):
            prop = match.property
            price_str = f"{float(prop.price):,.0f} ريال" if prop.price else "—"
            prop_lines.append(
                f"{i}. {prop.property_type} – {prop.district} – {price_str} ({int(match.score*100)}% مطابقة)\n"
                f"   🔗 {base_url}/property/{prop.pk}/"
            )
        budget_str = f"{float(req.budget):,.0f} ريال" if req.budget else "—"
        message = (
            f"السلام عليكم {req.name} 👋\n\n"
            f"بناءً على طلبك للبحث عن *{req.property_type}* في حي *{req.district}* بميزانية *{budget_str}*،\n"
            f"وجدنا *{matches.count()} عقار* يناسبك:\n\n"
            + "\n".join(prop_lines) +
            f"\n\nللاستفسار تواصل معنا مباشرةً.\nجودة المستقبل العقارية 🏠"
        )
        wa_url = f"https://wa.me/{req.phone}?text={quote(message)}"
        safe_msg = escape(message)
        changelist_url = admin_request.build_absolute_uri(reverse("admin:listings_propertyrequest_changelist"))
        return _whatsapp_preview_response(
            page_title=f"رسالة واتساب – {escape(req.name)}",
            heading="رسالة واتساب جاهزة للإرسال",
            meta_html=(
                f"العميل: <strong>{escape(req.name)}</strong> | الجوال: <strong>{escape(str(req.phone))}</strong>"
                f" | المطابقات: <strong>{matches.count()}</strong>"
            ),
            safe_message=safe_msg,
            wa_url=wa_url,
            changelist_url=changelist_url,
            back_button_title="العودة إلى قائمة طلبات بحث العقارات",
        )

    @admin.action(description="📞 تحديد حالة 'تم التواصل'")
    def mark_as_contacted(self, request, queryset):
        updated = queryset.update(status="contacted")
        self.message_user(request, f"تم تحديث {updated} طلب إلى 'تم التواصل'.", messages.SUCCESS)

    @admin.action(description="✅ تصنيف المحدد: مهتم (جاهز لعرض العقارات — ليس عرضاً منشوراً)")
    def segment_mark_interested(self, request, queryset):
        n = queryset.update(client_segment="interested")
        self.message_user(request, f"تم تصنيف {n} طلب كـ «مهتم».", messages.SUCCESS)

    @admin.action(description="🔍 تصنيف المحدد: عميل محتمل")
    def segment_mark_potential(self, request, queryset):
        n = queryset.update(client_segment="potential")
        self.message_user(request, f"تم تصنيف {n} طلب كـ «عميل محتمل».", messages.SUCCESS)

    @admin.action(description="⭐ تصنيف المحدد: طلب خاص")
    def segment_mark_special(self, request, queryset):
        n = queryset.update(client_segment="special")
        self.message_user(request, f"تم تصنيف {n} طلب كـ «طلب خاص».", messages.SUCCESS)

    @admin.action(description="↩ إعادة التصنيف: طلب بحث عادي")
    def segment_reset_search(self, request, queryset):
        n = queryset.update(client_segment="search")
        self.message_user(request, f"تم إعادة تصنيف {n} طلب إلى «طلب بحث — عادي».", messages.SUCCESS)


# ─────────────────────────────────────────────────────────────
# واجهة إدارة المطابقات (PropertyMatch)
# ─────────────────────────────────────────────────────────────
@admin.register(PropertyMatch)
class PropertyMatchAdmin(admin.ModelAdmin):
    list_display = ("id", "request_name", "property_link", "score_pct", "created_at")
    list_filter = ("created_at",)
    search_fields = ("request__name", "request__phone", "property__listing_id")
    readonly_fields = ("request", "property", "score", "created_at")
    ordering = ("-score", "-created_at")
    list_per_page = 50

    @admin.display(description="اسم العميل")
    def request_name(self, obj):
        url = reverse("admin:listings_propertyrequest_change", args=[obj.request.pk])
        return format_html('<a href="{}">{}</a>', url, obj.request.name)

    @admin.display(description="العقار")
    def property_link(self, obj):
        url = reverse("admin:listings_property_change", args=[obj.property.pk])
        return format_html('<a href="{}" target="_blank">{} – {}</a>', url, obj.property.listing_id or "—", obj.property.property_type)

    @admin.display(description="نسبة المطابقة")
    def score_pct(self, obj):
        pct = f"{obj.score * 100:.0f}"
        color = "#22C55E" if obj.score >= 0.8 else "#F59E0B" if obj.score >= 0.6 else "#9CA3AF"
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 10px;border-radius:10px;font-weight:700;">{}%</span>',
            color, pct,
        )


# ─────────────────────────────────────────────────────────────
# تنبيهات CRM (للمسوّقين داخل لوحة التحكم)
# ─────────────────────────────────────────────────────────────
@admin.register(CRMNotification)
class CRMNotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "is_read", "created_at")
    list_filter = ("is_read", "created_at", "user")
    search_fields = ("title", "message", "user__username", "user__email")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
    list_per_page = 50

    def has_view_permission(self, request, obj=None):
        if not request.user.is_active or not request.user.is_staff:
            return False
        if request.user.is_superuser:
            return True
        if obj is not None:
            return obj.user_id == request.user.id
        return True

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs.select_related("user")
        return qs.filter(user=request.user).select_related("user")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is not None:
            return obj.user_id == request.user.id
        return True

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff

# ─────────────────────────────────────────────────────────────
# شريط التنبيه المتحرك (واجهة الموقع)
# ─────────────────────────────────────────────────────────────
from django import forms


class SiteTickerAdminForm(forms.ModelForm):
    class Meta:
        model = SiteTicker
        fields = "__all__"
        widgets = {
            "background_color": forms.TextInput(attrs={"type": "color"}),
            "text_color": forms.TextInput(attrs={"type": "color"}),
            "message": forms.Textarea(attrs={"rows": 3, "style": "width:100%;"}),
        }


@admin.register(SiteTicker)
class SiteTickerAdmin(admin.ModelAdmin):
    form = SiteTickerAdminForm
    list_display = ("__str__", "is_enabled", "label", "background_color", "text_color", "updated_at")
    fieldsets = (
        ("الظهور", {
            "fields": ("is_enabled", "label", "message"),
            "description": "الشريط يظهر أسفل الهيدر مباشرة في الواجهة عندما يكون مفعّلاً ويوجد نص.",
        }),
        ("الألوان", {
            "fields": ("background_color", "text_color"),
        }),
    )
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not SiteTicker.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = SiteTicker.load()
        from django.shortcuts import redirect
        return redirect("../../listings/siteticker/%s/change/" % obj.pk)


# ─────────────────────────────────────────────────────────────
# البنر الإعلاني وسط العروض
# ─────────────────────────────────────────────────────────────
@admin.register(GeneralContact)
class GeneralContactAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "short_subject", "is_handled", "created_at")
    list_filter = ("is_handled", "created_at")
    search_fields = ("name", "phone", "subject")
    list_editable = ("is_handled",)
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)

    @admin.display(description="التفاصيل")
    def short_subject(self, obj):
        text = (obj.subject or "").strip()
        return text[:60] + ("…" if len(text) > 60 else "")


@admin.register(SiteAdBanner)
class SiteAdBannerAdmin(admin.ModelAdmin):
    list_display = ("__str__", "is_enabled", "insert_after", "link_url", "updated_at")
    fieldsets = (
        ("الظهور", {
            "fields": ("is_enabled", "insert_after", "alt_text", "link_url"),
            "description": "البنر يظهر داخل قائمة العروض بعد العدد المحدد من الكروت (افتراضياً بعد 3).",
        }),
        ("التصميم", {
            "fields": ("image",),
            "description": "اختياري. إن لم ترفع صورة يظهر تصميم متجاوب احترافي (كمبيوتر + جوال) بهوية الركن الأوسط وخدماتها. ارفع صورة فقط إذا أردت استبدال التصميم الافتراضي.",
        }),
        ("معلومات", {
            "fields": ("updated_at",),
        }),
    )
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not SiteAdBanner.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        from django.shortcuts import redirect
        obj = SiteAdBanner.load()
        return redirect(reverse("admin:listings_siteadbanner_change", args=[obj.pk]))

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff

