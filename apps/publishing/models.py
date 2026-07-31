import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class ChannelProvider(models.TextChoices):
    HARAJ = "haraj", "حراج"
    AQAR = "aqar", "عقار"
    X = "x", "X"


class JobStatus(models.TextChoices):
    PENDING = "pending", "بانتظار التنفيذ"
    RUNNING = "running", "قيد التنفيذ"
    REVIEW_READY = "review_ready", "جاهز للمراجعة"
    SUCCEEDED = "succeeded", "تم بنجاح"
    FAILED = "failed", "فشل"
    CANCELLED = "cancelled", "ملغي"


class ChannelConfig(models.Model):
    """
    Tenant-aware provider configuration.
    - company_key: معرف الشركة/النسخة البيضاء (slug أو tenant id كنص)
    - selectors: قاموس CSS/XPath/Text selectors
    - settings_json: أي خيارات إضافية للبوت/القناة
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company_key = models.CharField(
        "معرف الشركة",
        max_length=120,
        db_index=True,
        help_text="قيمة فريدة لكل شركة/نسخة White-label (مثال: acme-realestate).",
    )
    provider = models.CharField(
        "القناة",
        max_length=20,
        choices=ChannelProvider.choices,
        db_index=True,
    )
    name = models.CharField(
        "اسم الإعداد",
        max_length=120,
        default="default",
        help_text="اسم اختياري للإعداد إذا احتجت أكثر من إعداد للقناة نفسها.",
    )
    is_active = models.BooleanField("مفعل", default=True, db_index=True)

    selectors = models.JSONField(
        "Selectors",
        default=dict,
        blank=True,
        help_text="قاموس selectors الخاص بالقناة (مثال: title_input, continue_button...).",
    )
    settings_json = models.JSONField(
        "إعدادات إضافية",
        default=dict,
        blank=True,
        help_text="إعدادات تشغيل البوت (timeouts, headless, step toggles...).",
    )

    notes = models.TextField("ملاحظات", blank=True, default="")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_channel_configs",
        verbose_name="آخر تعديل بواسطة",
    )

    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "إعداد قناة نشر"
        verbose_name_plural = "إعدادات قنوات النشر"
        ordering = ["company_key", "provider", "-is_active", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company_key", "provider", "name"],
                name="uq_channel_config_company_provider_name",
            ),
        ]
        indexes = [
            models.Index(fields=["company_key", "provider", "is_active"]),
        ]

    def __str__(self) -> str:
        state = "مفعل" if self.is_active else "غير مفعل"
        return f"{self.company_key} | {self.get_provider_display()} | {self.name} ({state})"


class PublishingJob(models.Model):
    """
    Job model for async publishing workflow.
    Stores:
    - input payload (normalized)
    - runtime status transitions
    - adapter result/error payload
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company_key = models.CharField("معرف الشركة", max_length=120, db_index=True)
    provider = models.CharField("القناة", max_length=20, choices=ChannelProvider.choices, db_index=True)
    status = models.CharField("الحالة", max_length=20, choices=JobStatus.choices, default=JobStatus.PENDING, db_index=True)

    # مرجع داخلي للكيان المراد نشره (مثال: listings.Property)
    source_model = models.CharField("الموديل المصدر", max_length=120, blank=True, default="")
    source_object_id = models.CharField("معرف الكيان المصدر", max_length=64, blank=True, default="", db_index=True)

    channel_config = models.ForeignKey(
        ChannelConfig,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="jobs",
        verbose_name="إعداد القناة المستخدم",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="publishing_jobs",
        verbose_name="أنشئ بواسطة",
    )

    payload = models.JSONField(
        "بيانات الإدخال",
        default=dict,
        blank=True,
        help_text="الـ payload القياسي الذي يتم تسليمه للـ adapter.",
    )
    result = models.JSONField(
        "نتيجة التنفيذ",
        default=dict,
        blank=True,
        help_text="النتيجة النهائية/الوسيطة (review_url, external_id, artifacts...).",
    )
    error_details = models.JSONField(
        "تفاصيل الخطأ",
        default=dict,
        blank=True,
        help_text="تفاصيل تقنية للخطأ عند الفشل.",
    )

    attempts = models.PositiveIntegerField("عدد المحاولات", default=0)
    max_attempts = models.PositiveIntegerField("الحد الأقصى للمحاولات", default=3)
    priority = models.PositiveSmallIntegerField("الأولوية", default=5, db_index=True)

    queued_at = models.DateTimeField("وقت الإدراج بالطابور", null=True, blank=True)
    started_at = models.DateTimeField("وقت بدء التنفيذ", null=True, blank=True)
    finished_at = models.DateTimeField("وقت الانتهاء", null=True, blank=True)
    next_retry_at = models.DateTimeField("موعد إعادة المحاولة", null=True, blank=True, db_index=True)

    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "مهمة نشر"
        verbose_name_plural = "مهام النشر"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company_key", "provider", "status"]),
            models.Index(fields=["status", "next_retry_at"]),
            models.Index(fields=["source_model", "source_object_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.company_key} | {self.provider} | {self.status} | {self.id}"

    @property
    def is_terminal(self) -> bool:
        return self.status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}

    def mark_running(self) -> None:
        self.status = JobStatus.RUNNING
        self.attempts += 1
        if not self.started_at:
            self.started_at = timezone.now()
        self.save(update_fields=["status", "attempts", "started_at", "updated_at"])

    def mark_review_ready(self, result: dict | None = None) -> None:
        self.status = JobStatus.REVIEW_READY
        self.finished_at = timezone.now()
        if result is not None:
            self.result = result
        # Clear retry/error metadata once a usable review state is reached.
        self.error_details = {}
        self.next_retry_at = None
        self.save(update_fields=["status", "finished_at", "result", "error_details", "next_retry_at", "updated_at"])

    def mark_succeeded(self, result: dict | None = None) -> None:
        self.status = JobStatus.SUCCEEDED
        self.finished_at = timezone.now()
        if result is not None:
            self.result = result
        # Ensure successful jobs do not keep stale failure diagnostics.
        self.error_details = {}
        self.next_retry_at = None
        self.save(update_fields=["status", "finished_at", "result", "error_details", "next_retry_at", "updated_at"])

    def mark_failed(self, error_details: dict | None = None, retry_delay_seconds: int = 60) -> None:
        now = timezone.now()
        self.status = JobStatus.FAILED
        self.finished_at = now
        if error_details is not None:
            self.error_details = error_details
        if self.attempts < self.max_attempts:
            self.next_retry_at = now + timedelta(seconds=retry_delay_seconds)
        self.save(update_fields=["status", "finished_at", "error_details", "next_retry_at", "updated_at"])
