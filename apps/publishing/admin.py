import json
from typing import Any

from django.contrib import admin, messages
from django import forms
from django.db.models import QuerySet
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from pydantic import ValidationError as PydanticValidationError

from apps.publishing.configs.config_resolver import SelectorSchema
from apps.publishing.models import ChannelConfig, JobStatus, PublishingJob
from apps.publishing.services.publisher_service import PublisherService


def _pretty_json(value: Any) -> str:
    try:
        return json.dumps(value or {}, ensure_ascii=False, indent=2, sort_keys=True)
    except TypeError:
        return str(value)


class TenantIdListFilter(admin.SimpleListFilter):
    """Filter jobs/config by tenant/company key."""

    title = _("tenant_id")
    parameter_name = "tenant_id"

    def lookups(self, request, model_admin):
        keys = (
            model_admin.model.objects.order_by()
            .values_list("company_key", flat=True)
            .distinct()[:50]
        )
        return [(k, k) for k in keys]

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        return queryset.filter(company_key=value)


class ChannelConfigAdminForm(forms.ModelForm):
    """
    Admin form with strict selectors JSON validation using Pydantic schema.
    """

    class Meta:
        model = ChannelConfig
        fields = "__all__"

    def clean_selectors(self):
        selectors = self.cleaned_data.get("selectors") or {}
        try:
            # Validate required/optional selectors shape.
            SelectorSchema.model_validate(selectors)
        except PydanticValidationError as exc:
            messages_lines = []
            for err in exc.errors():
                loc = ".".join(str(x) for x in err.get("loc", [])) or "selectors"
                msg = err.get("msg", "invalid value")
                messages_lines.append(f"- {loc}: {msg}")
            details = "\n".join(messages_lines) or str(exc)
            raise forms.ValidationError(
                "JSON غير صالح في حقل selectors. يرجى تصحيح الأخطاء التالية:\n" + details
            )
        return selectors


@admin.action(description="إعادة تشغيل المهام الفاشلة (Retry)")
def retry_failed_jobs(modeladmin, request, queryset: QuerySet[PublishingJob]):
    retried = 0
    skipped = 0

    for job in queryset:
        if job.status != JobStatus.FAILED:
            skipped += 1
            continue
        try:
            PublisherService.retry(str(job.id))
            retried += 1
        except Exception:
            skipped += 1

    if retried:
        modeladmin.message_user(
            request,
            f"تمت إعادة جدولة {retried} مهمة فاشلة بنجاح.",
            level=messages.SUCCESS,
        )
    if skipped:
        modeladmin.message_user(
            request,
            f"تم تخطي {skipped} مهمة (ليست فاشلة أو تعذر إعادة تشغيلها).",
            level=messages.WARNING,
        )


@admin.register(PublishingJob)
class PublishingJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant_id_display",
        "provider",
        "status_badge",
        "attempts_progress",
        "source_model",
        "source_object_id",
        "created_at",
        "updated_at",
    )
    list_display_links = ("id",)
    list_filter = ("status", "provider", TenantIdListFilter, "created_at")
    search_fields = (
        "id",
        "company_key",
        "source_model",
        "source_object_id",
    )
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "queued_at",
        "started_at",
        "finished_at",
        "next_retry_at",
        "status_badge",
        "payload_pretty",
        "result_pretty",
        "error_details_pretty",
    )
    actions = (retry_failed_jobs,)
    ordering = ("-created_at",)
    list_per_page = 30

    fieldsets = (
        ("معلومات أساسية", {
            "fields": (
                "id",
                "company_key",
                "provider",
                "status",
                "status_badge",
                "channel_config",
                "created_by",
            )
        }),
        ("المرجع الداخلي", {
            "fields": ("source_model", "source_object_id")
        }),
        ("التنفيذ والمحاولات", {
            "fields": (
                "attempts",
                "max_attempts",
                "priority",
                "queued_at",
                "started_at",
                "finished_at",
                "next_retry_at",
            )
        }),
        ("البيانات", {
            "fields": ("payload", "payload_pretty", "result", "result_pretty", "error_details", "error_details_pretty")
        }),
        ("التواريخ", {"fields": ("created_at", "updated_at")}),
    )

    def tenant_id_display(self, obj: PublishingJob) -> str:
        return obj.company_key

    tenant_id_display.short_description = "Tenant ID"
    tenant_id_display.admin_order_field = "company_key"

    def attempts_progress(self, obj: PublishingJob) -> str:
        return f"{obj.attempts}/{obj.max_attempts}"

    attempts_progress.short_description = "محاولات"

    def status_badge(self, obj: PublishingJob):
        palette = {
            JobStatus.PENDING: ("#334155", "#e2e8f0"),
            JobStatus.RUNNING: ("#1d4ed8", "#dbeafe"),
            JobStatus.REVIEW_READY: ("#0f766e", "#ccfbf1"),
            JobStatus.SUCCEEDED: ("#166534", "#dcfce7"),
            JobStatus.FAILED: ("#991b1b", "#fee2e2"),
            JobStatus.CANCELLED: ("#6b7280", "#f3f4f6"),
        }
        bg, fg = palette.get(obj.status, ("#374151", "#f9fafb"))
        label = obj.get_status_display()
        return format_html(
            '<span style="background:{};color:{};padding:4px 10px;border-radius:999px;font-weight:700;">{}</span>',
            bg,
            fg,
            label,
        )

    status_badge.short_description = "الحالة"

    def payload_pretty(self, obj: PublishingJob):
        return format_html("<pre style='white-space:pre-wrap;direction:ltr;text-align:left;'>{}</pre>", _pretty_json(obj.payload))

    payload_pretty.short_description = "Payload (formatted)"

    def result_pretty(self, obj: PublishingJob):
        return format_html("<pre style='white-space:pre-wrap;direction:ltr;text-align:left;'>{}</pre>", _pretty_json(obj.result))

    result_pretty.short_description = "Result (formatted)"

    def error_details_pretty(self, obj: PublishingJob):
        if not obj.error_details:
            return mark_safe('<span style="color:#64748b;">لا توجد أخطاء مسجلة.</span>')
        return format_html(
            "<pre style='white-space:pre-wrap;direction:ltr;text-align:left;color:#fecaca;background:#450a0a;padding:10px;border-radius:8px;'>{}</pre>",
            _pretty_json(obj.error_details),
        )

    error_details_pretty.short_description = "Error Details (formatted)"


@admin.register(ChannelConfig)
class ChannelConfigAdmin(admin.ModelAdmin):
    form = ChannelConfigAdminForm
    list_display = (
        "company_key",
        "provider",
        "name",
        "is_active",
        "updated_by",
        "updated_at",
    )
    list_filter = ("provider", "is_active", TenantIdListFilter, "updated_at")
    search_fields = ("company_key", "name", "provider", "notes")
    readonly_fields = ("id", "created_at", "updated_at", "selectors_pretty", "settings_pretty")
    ordering = ("company_key", "provider", "-is_active", "name")
    list_per_page = 30

    fieldsets = (
        ("التعريف", {
            "fields": ("id", "company_key", "provider", "name", "is_active")
        }),
        ("Selectors", {
            "description": "أدخل JSON selectors الخام هنا. العرض المنسق يظهر أسفل الحقل.",
            "fields": ("selectors", "selectors_pretty"),
        }),
        ("إعدادات إضافية", {
            "fields": ("settings_json", "settings_pretty"),
        }),
        ("حوكمة", {
            "fields": ("notes", "updated_by", "created_at", "updated_at"),
        }),
    )

    def save_model(self, request, obj: ChannelConfig, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def selectors_pretty(self, obj: ChannelConfig):
        return format_html("<pre style='white-space:pre-wrap;direction:ltr;text-align:left;'>{}</pre>", _pretty_json(obj.selectors))

    selectors_pretty.short_description = "Selectors (formatted)"

    def settings_pretty(self, obj: ChannelConfig):
        return format_html("<pre style='white-space:pre-wrap;direction:ltr;text-align:left;'>{}</pre>", _pretty_json(obj.settings_json))

    settings_pretty.short_description = "Settings (formatted)"

