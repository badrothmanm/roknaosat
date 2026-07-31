import random
import string
import uuid
from django.db import models
from django.urls import reverse
from django.utils import timezone
from listings.media_fields import media_image_field

# =====================================================
# UTILITIES
# =====================================================

def generate_unique_listing_id():
    """توليد رقم تعريفي فريد للعقار مكون من 6 خانات"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# =====================================================
# USER ACCESS PROFILE (نموذج صلاحيات دخول المستخدم)
# =====================================================

class UserAccessProfile(models.Model):
    user = models.OneToOneField(
        "auth.User", 
        on_delete=models.CASCADE, 
        related_name='access_profile', 
        verbose_name="المستخدم"
    )
    access_start_date = models.DateField("تاريخ بداية الصلاحية", null=True, blank=True)
    access_end_date = models.DateField("تاريخ نهاية الصلاحية", null=True, blank=True)
    notification_email = models.EmailField(
        "بريد التنبيهات",
        max_length=254,
        blank=True,
        null=True,
        help_text="يُستلم عليه تنبيهات الطلبات والإسناد. إن تُرك فارغاً يُستخدم بريد حساب المستخدم.",
    )
    allow_add_users = models.BooleanField(
        "إضافة مستخدمين",
        default=True,
        help_text="إن أُلغيَ التحديد: لا يمكن لهذا الحساب إنشاء مستخدمين جدد من الإدارة.",
    )
    allow_change_passwords = models.BooleanField(
        "تغيير كلمات المرور والصلاحيات",
        default=True,
        help_text="إن أُلغيَ التحديد: لا يمكنه تغيير كلمات المرور، ولا تعديل صلاحيات المستخدمين أو المجموعات أو ترقية حساب لموظف/مدير.",
    )

    class Meta:
        verbose_name = "صلاحية دخول مستخدم"
        verbose_name_plural = "صلاحيات دخول المستخدمين"

    def __str__(self):
        return f"صلاحيات {self.user.username}"


# =====================================================
# PROPERTY MODEL (نموذج العقار الرئيسي)
# =====================================================

class Property(models.Model):
    class Meta:
        verbose_name = "عقار"
        verbose_name_plural = "العقارات"

    OFFER_TYPES = [('بيع', 'بيع'), ('إيجار', 'إيجار'), ('إستثمار', 'إستثمار')]
    PROPERTY_TYPES = [
        ('فيلا', 'فيلا'), ('شقة', 'شقة'), ('عمارة', 'عمارة'),
        ('قصر', 'قصر'), ('دور', 'دور'), ('أرض', 'أرض'),
        ('مزرعة', 'مزرعة'), ('استراحة', 'استراحة'), ('محل تجاري', 'محل تجاري')
    ]
    USAGE_TYPES = [('سكني', 'سكني'), ('تجاري', 'تجاري')]
    STATUS_CHOICES = [
        ('متاح', 'متاح'), 
        ('مباع', 'مباع'), 
        ('مؤجر', 'مؤجر'),
        ('قيد التفاوض', 'قيد التفاوض'),
        ('انتهت الفرصة', 'انتهت الفرصة')
    ]
    VISIBILITY_CHOICES = [('منشور', 'منشور'), ('مخفي', 'مخفي')]

    listing_id = models.CharField(
        "رقم العقار", 
        max_length=10, 
        unique=True, 
        editable=False, 
        null=True, 
        blank=True
    )

    full_name = models.CharField("الاسم الكامل", max_length=255)
    phone = models.CharField("رقم الجوال", max_length=20)
    city = models.CharField("المدينة", max_length=50, default="جدة")
    district = models.CharField("الحي", max_length=100, null=True, blank=True)

    property_type = models.CharField("نوع العقار", max_length=50, choices=PROPERTY_TYPES)
    offer_type = models.CharField("نوع العرض", max_length=20, choices=OFFER_TYPES)
    category = models.CharField("التصنيف", max_length=20, choices=USAGE_TYPES, null=True, blank=True)

    map_url = models.TextField("رابط الخريطة", null=True, blank=True)
    video_url = models.URLField("رابط الفيديو (يوتيوب/تيك توك)", max_length=500, null=True, blank=True)
    video_enabled = models.BooleanField("تفعيل الفيديو للزوار", default=True)
    show_map_to_visitors = models.BooleanField("إظهار الخريطة للزوار", default=False)
    
    # التحكم في ظهور السعر للزوار
    NEGOTIATION_CHOICES = [
        ('قابل للتفاوض', 'قابل للتفاوض'),
        ('غير قابل للتفاوض', 'غير قابل للتفاوض'),
        ('على السوم', 'على السوم')
    ]

    show_price_to_visitors = models.BooleanField("إظهار السعر للزوار", default=True)
    negotiation_status = models.CharField("حالة السعر", max_length=50, choices=NEGOTIATION_CHOICES, null=True, blank=True)

    visibility = models.CharField("حالة الظهور", max_length=20, choices=VISIBILITY_CHOICES, default='منشور')

    # QR Card specific fields
    val_license = models.CharField("رقم رخصة فال", max_length=50, null=True, blank=True)
    ad_number = models.CharField("رقم الإعلان", max_length=50, null=True, blank=True)

    source_offer = models.OneToOneField(
        "PropertyOffer", 
        verbose_name="الطلب المصدر",
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="published_property"
    )

    owner_notes = models.CharField("ملاحظات المالك", max_length=180, null=True, blank=True)

    area = models.DecimalField("المساحة", max_digits=10, decimal_places=2)
    price = models.DecimalField("السعر", max_digits=18, decimal_places=2)

    property_age = models.CharField("عمر العقار", max_length=50, null=True, blank=True)
    floors = models.IntegerField("عدد الأدوار", null=True, blank=True)
    rooms = models.IntegerField("عدد الغرف", null=True, blank=True)
    apartments = models.IntegerField("عدد الشقق", null=True, blank=True)
    bathrooms = models.IntegerField("عدد دورات المياه", null=True, blank=True)

    # صور العقار (محلي أو Cloudinary حسب الإعدادات)
    image1 = media_image_field("صورة 1", "property_images/")
    image2 = media_image_field("صورة 2", "property_images/")
    image3 = media_image_field("صورة 3", "property_images/")
    image4 = media_image_field("صورة 4", "property_images/")
    image5 = media_image_field("صورة 5", "property_images/")
    image6 = media_image_field("صورة 6", "property_images/")
    image7 = media_image_field("صورة 7", "property_images/")
    image8 = media_image_field("صورة 8", "property_images/")
    image9 = media_image_field("صورة 9", "property_images/")
    image10 = media_image_field("صورة 10", "property_images/")
    cover_image_slot = models.PositiveSmallIntegerField(
        "صورة الغلاف (رقم الصورة)",
        null=True,
        blank=True,
        help_text="اختر رقم الصورة التي تريدها كغلاف (سيتم عرضها أولاً في المعرض).",
    )

    status = models.CharField("الحالة", max_length=20, choices=STATUS_CHOICES, default='متاح')
    inquiry_count = models.IntegerField("عدد الاستفسارات", default=0)
    created_at = models.DateTimeField("تاريخ الإضافة", auto_now_add=True)

    # --- Properties & Methods ---

    @property
    def embed_video_url(self):
        """تحويل رابط يوتيوب أو تيك توك العادي إلى رابط صالح للتضمين (Embed)"""
        if not self.video_enabled:
            return None
        if not self.video_url:
            return None
        
        import re
        
        # 1. YouTube
        yt_match = re.search(r'(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([^"&?\/\s]{11})', self.video_url)
        if yt_match:
            video_id = yt_match.group(1)
            return f"https://www.youtube.com/embed/{video_id}?enablejsapi=1"
            
        # 2. TikTok
        tt_match = re.search(r'tiktok\.com\/.*\/video\/(\d+)', self.video_url)
        if tt_match:
            video_id = tt_match.group(1)
            return f"https://www.tiktok.com/embed/v2/{video_id}"
            
        # إذا كان الرابط لمنصة مدعومة ولكن غير صالح للتضمين أو لم نتمكن من استخراج المعرف
        if 'youtube.com' in self.video_url or 'youtu.be' in self.video_url or 'tiktok.com' in self.video_url:
            if '/embed/' in self.video_url:
                return self.video_url
            return None
            
        # إرجاع الرابط الأصلي لأي منصات أخرى
        return self.video_url

    @property
    def display_price(self):
        """يعيد السعر إذا كان مسموحاً بعرضه، وإلا يعيد نص 'عند التواصل' أو None"""
        if self.show_price_to_visitors and self.price:
            return self.price
        return None

    @property
    def all_images(self):
        """إرجاع قائمة بكافة الصور غير الفارغة"""
        by_slot = {}
        for i in range(1, 11):
            img = getattr(self, f"image{i}")
            if img:
                by_slot[i] = img

        if not by_slot:
            return []

        cover = self.cover_image_slot
        out = []
        if cover in by_slot:
            out.append(by_slot.pop(cover))
        for i in sorted(by_slot.keys()):
            out.append(by_slot[i])
        return out

    def get_absolute_url(self):
        return reverse('listings:property-detail', kwargs={'pk': self.pk})

    def save(self, *args, **kwargs):
        """توليد معرف فريد عند الحفظ لأول مرة"""
        if not self.listing_id:
            while True:
                # استخدمنا الدالة التي عرفتها في الأعلى لتوحيد المنطق
                new_id = generate_unique_listing_id()
                if not Property.objects.filter(listing_id=new_id).exists():
                    self.listing_id = new_id
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.listing_id or 'N/A'} - {self.property_type} - {self.full_name}"


# =====================================================
# PROPERTY OFFER (نموذج طلب تسويق عقار من المالك)
# =====================================================

class PropertyOffer(models.Model):
    class Meta:
        verbose_name = "طلب تسويق عقار"
        verbose_name_plural = "طلبات تسويق العقارات"

    class Status(models.TextChoices):
        NEW = "new", "جديد"
        CONTACTED = "contacted", "تم التواصل"
        UNDER_REVIEW = "under_review", "قيد المراجعة"
        APPROVED = "approved", "مقبول"
        REJECTED = "rejected", "مرفوض"
        OWNER_REVIEW = "owner_review", "مراجعة صاحب العقار"
        PUBLISHED = "published", "تم نشره"

    owner_name = models.CharField("اسم المالك", max_length=255, null=True, blank=True)
    phone = models.CharField("رقم الجوال", max_length=20, null=True, blank=True)

    whatsapp_url = models.TextField("رابط الواتساب", null=True, blank=True)
    video_link = models.TextField("رابط الفيديو", null=True, blank=True)
    video_enabled = models.BooleanField("تفعيل الفيديو للزوار", default=True)
    images_link = models.TextField("رابط الصور", null=True, blank=True)
    google_map = models.TextField("موقع خرائط جوجل", null=True, blank=True)

    city = models.CharField("المدينة", max_length=50, null=True, blank=True)
    neighborhood = models.CharField("الحي", max_length=100, null=True, blank=True)
    property_type = models.CharField("نوع العقار", max_length=50, null=True, blank=True)
    property_age = models.CharField("عمر العقار", max_length=50, null=True, blank=True)
    listing_type = models.CharField("نوع العرض", max_length=20, null=True, blank=True)
    category = models.CharField("التصنيف", max_length=20, null=True, blank=True)

    area = models.CharField("المساحة", max_length=50, null=True, blank=True)
    price = models.CharField("السعر", max_length=50, null=True, blank=True)

    floors = models.IntegerField("عدد الأدوار", default=0)
    apartments = models.IntegerField("عدد الشقق", default=0)
    rooms = models.IntegerField("عدد الغرف", default=0)
    bathrooms = models.IntegerField("عدد دورات المياه", default=0)

    owner_notes = models.TextField("ملاحظات المالك", null=True, blank=True)

    status = models.CharField(
        "الحالة",
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True
    )

    assigned_to = models.ForeignKey(
        "auth.User",
        verbose_name="مسند إلى",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_offers",
    )

    created_at = models.DateTimeField("تاريخ الطلب", auto_now_add=True)

    def __str__(self):
        return f"طلب #{self.pk} - {self.owner_name}"


# =====================================================
# PROPERTY REQUEST IMAGE (نموذج صور الطلبات)
# =====================================================

class PropertyRequestImage(models.Model):
    class Meta:
        ordering = ['sort_order', 'created_at']
        verbose_name = "صورة طلب عقار"
        verbose_name_plural = "صور طلبات العقارات"

    request = models.ForeignKey(PropertyOffer, verbose_name="الطلب", on_delete=models.CASCADE, related_name='images')
    image = media_image_field("الصورة", "property_requests/")

    is_cover = models.BooleanField("صورة الغلاف", default=False)
    sort_order = models.IntegerField("ترتيب العرض", default=0)
    created_at = models.DateTimeField("تاريخ الإضافة", auto_now_add=True)

    def save(self, *args, **kwargs):
        """التأكد من وجود صورة غلاف واحدة فقط للطلب الواحد"""
        if self.is_cover:
            PropertyRequestImage.objects.filter(
                request=self.request,
                is_cover=True
            ).exclude(pk=self.pk).update(is_cover=False)
        super().save(*args, **kwargs)


# =====================================================
# PROPERTY LEAD (نموذج العملاء المحتملين)
# =====================================================

class PropertyLead(models.Model):
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "عميل محتمل"
        verbose_name_plural = "العملاء المحتملين"

    property = models.ForeignKey(
        "Property", 
        verbose_name="العقار", 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name="leads"
    )
    name = models.CharField("الاسم", max_length=120, null=True, blank=True)
    phone = models.CharField("رقم الجوال", max_length=20, null=True, blank=True)
    message = models.TextField("الرسالة", blank=True, null=True)
    source = models.CharField("المصدر", max_length=50, blank=True, null=True)
    ip_address = models.GenericIPAddressField("عنوان IP", blank=True, null=True)
    created_at = models.DateTimeField("تاريخ الطلب", default=timezone.now)
    
    class Status(models.TextChoices):
        NEW = "new", "جديد"
        INTERESTED = "interested", "عميل مهتم"
        NOT_INTERESTED = "not_interested", "عميل غير مهتم"
        NEUTRAL = "neutral", "عميل محايد"
        SPECIAL_REQUEST = "special_request", "عميل له طلب خاص"

    status = models.CharField(
        "الحالة",
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True
    )

    assigned_to = models.ForeignKey(
        "auth.User",
        verbose_name="مسند إلى",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_leads",
    )

    smart_link = models.ForeignKey(
        "PropertySmartLink",
        verbose_name="الرابط الذكي المصدر",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads"
    )

    def __str__(self):
        return f"{self.name} - {self.phone}"


# =====================================================
# SMART BROCHURE LINK (رابط البروشور الذكي للتسويق)
# =====================================================

class PropertySmartLink(models.Model):
    class Meta:
        verbose_name = "رابط ذكي"
        verbose_name_plural = "الروابط الذكية"

    property = models.ForeignKey(
        "Property",
        verbose_name="العقار",
        on_delete=models.CASCADE,
        related_name="smart_links"
    )
    marketer = models.ForeignKey(
        "auth.User",
        verbose_name="المسوق",
        on_delete=models.CASCADE,
        related_name="smart_links",
        null=True,
        blank=True
    )
    token = models.CharField("الرمز الفريد", max_length=20, unique=True)
    views = models.IntegerField("عدد المشاهدات", default=0)
    inquiry_count = models.IntegerField("عدد الاستفسارات", default=0)
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.token:
            while True:
                # توليد رمز عشوائي للرابط القصير
                new_token = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
                if not PropertySmartLink.objects.filter(token=new_token).exists():
                    self.token = new_token
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        marketer_name = self.marketer.username if self.marketer else "عام"
        return f"رابط ({marketer_name}) لـ {self.property.listing_id} - مشاهدات: {self.views}"

    class Meta:
        verbose_name = "رابط ذكي"
        verbose_name_plural = "الروابط الذكية"
        unique_together = ('property', 'marketer')

    def get_absolute_url(self):
        return reverse('listings:smart-brochure', kwargs={'token': self.token})


class SmartLinkViewLog(models.Model):
    """
    سجل لمتابعة المشاهدات الحقيقية والفريدة لكل رابط ذكي.
    يستخدم لمنع تكرار الاحتساب لنفس الشخص في فترة زمنية قصيرة.
    """
    smart_link = models.ForeignKey(PropertySmartLink, on_delete=models.CASCADE, related_name="view_logs", verbose_name="الرابط الذكي")
    ip_address = models.GenericIPAddressField("عنوان IP")
    user_agent = models.TextField("برنامج المتصفح", null=True, blank=True)
    created_at = models.DateTimeField("وقت المشاهدة", auto_now_add=True)

    class Meta:
        verbose_name = "سجل مشاهدة رابط ذكي"
        verbose_name_plural = "سجلات مشاهدات الروابط الذكية"
        indexes = [
            models.Index(fields=['smart_link', 'ip_address', 'created_at']),
        ]

    def __str__(self):
        return f"{self.smart_link.token} - {self.ip_address}"


# =====================================================
# FAST REQUEST (نموذج الطلبات السريعة من البطاقة الذكية)
# =====================================================

class FastRequest(models.Model):
    class Meta:
        verbose_name = "طلب سريع"
        verbose_name_plural = "الطلبات السريعة"
        ordering = ["-created_at"]

    name = models.CharField("الاسم", max_length=100)
    phone = models.CharField("رقم الجوال", max_length=20)
    request_text = models.TextField("نص الطلب")
    created_at = models.DateTimeField("تاريخ الطلب", auto_now_add=True)
    is_read = models.BooleanField("مقروء", default=False)

    assigned_to = models.ForeignKey(
        "auth.User",
        verbose_name="مسند إلى",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_fast_requests",
    )
    
    smart_link = models.ForeignKey(
        "PropertySmartLink",
        verbose_name="الرابط الذكي المصدر",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fast_requests"
    )

    def __str__(self):
        return f"طلب من {self.name} - {self.phone}"


# =====================================================
# PROPERTY REQUEST (نموذج طلبات البحث عن عقار)
# =====================================================

class PropertyRequest(models.Model):
    """
    طلب بحث عن عقار — موحّد لمصادر: الموقع، دردشة AI، واتساب، يدوي.
    """

    class Meta:
        verbose_name = "طلب عقار"
        verbose_name_plural = "طلبات العقارات"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["property_type", "district", "budget"]),
            models.Index(fields=["status", "match_score"]),
            models.Index(fields=["property_type"]),
            models.Index(fields=["district"]),
            models.Index(fields=["budget"]),
            models.Index(fields=["source"]),
            # Dedup fingerprint (phone + نوع + حي + ميزانية) — priority مفهرس عبر db_index على الحقل
            models.Index(fields=["phone", "property_type", "district", "budget"]),
        ]

    # مصدر الطلب (موحّد للـ API والواجهات)
    SOURCE_CHOICES = [
        ("website", "Website"),
        ("ai_chat", "AI Chat"),
        ("whatsapp", "WhatsApp"),
        ("manual", "Manual"),
    ]

    # تصنيف السكن (عائلي / فردي) — منفصل عن client_segment الإداري
    HOUSEHOLD_CATEGORY_CHOICES = [
        ("family", "عائلي"),
        ("single", "فردي"),
    ]

    PRIORITY_CHOICES = [
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ]

    STATUS_CHOICES = [
        ("new", "جديد - غير معالج"),
        ("working", "قيد العمل / في المهام"),
        ("contacted", "تم التواصل مع العميل"),
        ("matched", "تمت المطابقة"),
        ("closed", "مغلق - تم الإنجاز"),
        ("lost", "مفقود / غير جاد"),
    ]

    # يفصل طلبات البحث عن عقار عن «عروض» المنشورة وعن مسارات العملاء المحتملين الأخرى
    CLIENT_SEGMENT_CHOICES = [
        ("search", "طلب بحث — عادي"),
        ("potential", "عميل محتمل"),
        ("interested", "مهتم"),
        ("special", "طلب خاص"),
    ]

    REQUEST_TYPES = [('شراء', 'شراء'), ('إيجار', 'إيجار'), ('إستثمار', 'إستثمار')]
    USAGE_TYPES = [('سكني', 'سكني'), ('تجاري', 'تجاري')]

    name = models.CharField("اسم العميل", max_length=255)
    phone = models.CharField("رقم الجوال", max_length=20)
    property_type = models.CharField("نوع العقار", max_length=50, choices=Property.PROPERTY_TYPES)
    district = models.CharField("الحي / الأحياء", max_length=500)
    budget = models.DecimalField("الميزانية", max_digits=18, decimal_places=2, null=True, blank=True)

    # --- Technical Specifications ---
    request_type = models.CharField("نوع الطلب", max_length=20, choices=REQUEST_TYPES, null=True, blank=True)
    usage_type = models.CharField("نوع الاستخدام", max_length=20, choices=USAGE_TYPES, null=True, blank=True)
    city = models.CharField("المدينة", max_length=50, default="الرياض", null=True, blank=True)
    area = models.CharField("المساحة المطلوبة", max_length=50, null=True, blank=True)
    property_age = models.CharField("عمر العقار المفضل", max_length=50, null=True, blank=True)
    
    floors_count = models.CharField("عدد الأدوار", max_length=20, null=True, blank=True)
    apartments_count = models.CharField("عدد الشقق", max_length=20, null=True, blank=True)
    rooms_count = models.CharField("عدد الغرف", max_length=20, null=True, blank=True)
    bathrooms_count = models.CharField("عدد دورات المياه", max_length=20, null=True, blank=True)

    # حقول موحّدة للـ API (رقمي/منطقي أوضح من النصوص القديمة)
    rooms = models.PositiveSmallIntegerField("عدد الغرف", null=True, blank=True)
    furnished = models.BooleanField("مفروش", null=True, blank=True)
    category = models.CharField(
        "تصنيف السكن",
        max_length=16,
        choices=HOUSEHOLD_CATEGORY_CHOICES,
        null=True,
        blank=True,
        help_text="عائلي / فردي — اختياري.",
    )
    conversation_id = models.CharField(
        "معرف المحادثة",
        max_length=128,
        null=True,
        blank=True,
        db_index=True,
        help_text="مثلاً جلسة بوت أو واتساب.",
    )

    status = models.CharField("الحالة", max_length=20, choices=STATUS_CHOICES, default="new", db_index=True)
    client_segment = models.CharField(
        "تصنيف العميل",
        max_length=32,
        choices=CLIENT_SEGMENT_CHOICES,
        default="search",
        db_index=True,
        help_text="طلب بحث عادي / عميل محتمل / مهتم / طلب خاص — منفصل عن عروض العقارات المنشورة.",
    )
    source = models.CharField(
        "المصدر",
        max_length=20,
        choices=SOURCE_CHOICES,
        default="website",
        db_index=True,
        help_text="مصدر إنشاء الطلب.",
    )
    notes = models.TextField("ملاحظات إضافية", null=True, blank=True)

    # Lead scoring (مستقل عن match_score الخاص بمحرك المطابقة مع العقارات)
    score = models.FloatField(
        "درجة الصلاحية (Lead)",
        default=0.0,
        help_text="0–100 حسب الميزانية، اكتمال البيانات، والحي.",
    )
    priority = models.CharField(
        "الأولوية",
        max_length=16,
        choices=PRIORITY_CHOICES,
        default="low",
        db_index=True,
    )

    match_score = models.FloatField("أعلى نسبة مطابقة", default=0.0)
    matched_count = models.IntegerField("عدد العقارات المطابقة", default=0)

    assigned_to = models.ForeignKey(
        "auth.User",
        verbose_name="مسند إلى",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_requests",
    )

    created_at = models.DateTimeField("تاريخ الطلب", auto_now_add=True)
    updated_at = models.DateTimeField("تاريخ التحديث", auto_now=True)

    def __str__(self):
        return f"طلب {self.property_type} ({self.district}) - {self.name}"


# =====================================================
# PROPERTY MATCH (نموذج المطابقات الوسيط)
# =====================================================

class PropertyMatch(models.Model):
    class Meta:
        verbose_name = "مطابقة عقار"
        verbose_name_plural = "مطابقات العقارات"
        ordering = ["-score", "-created_at"]
        unique_together = [("request", "property")]

    request = models.ForeignKey(
        PropertyRequest,
        verbose_name="الطلب",
        on_delete=models.CASCADE,
        related_name="matches",
    )
    property = models.ForeignKey(
        Property,
        verbose_name="العقار",
        on_delete=models.CASCADE,
        related_name="request_matches",
    )
    score = models.FloatField("نسبة المطابقة")
    created_at = models.DateTimeField("تاريخ المطابقة", auto_now_add=True)

    def __str__(self):
        return f"مطابقة: {self.request.name} ← {self.property.listing_id} ({self.score * 100:.0f}%)"


# =====================================================
# PROPERTY BOOKING (نموذج طلبات الحجز والمعاينة)
# =====================================================

class PropertyBooking(models.Model):
    class Meta:
        verbose_name = "طلب حجز/معاينة"
        verbose_name_plural = "طلبات الحجز والمعاينة"
        ordering = ["-created_at"]

    property = models.ForeignKey(
        "Property",
        verbose_name="العقار",
        on_delete=models.CASCADE,
        related_name="bookings"
    )
    name = models.CharField("اسم العميل", max_length=255)
    phone = models.CharField("رقم الجوال", max_length=20)
    booking_date = models.DateField("تاريخ المعاينة")
    booking_time = models.TimeField("وقت المعاينة")
    notes = models.TextField("ملاحظات", null=True, blank=True)
    created_at = models.DateTimeField("تاريخ الطلب", auto_now_add=True)

    def __str__(self):
        return f"حجز {self.property.listing_id or 'N/A'} - {self.name} ({self.booking_date})"


# =====================================================
# APPOINTMENT (نظام المواعيد للزوار)
# =====================================================
class Appointment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "قيد المراجعة"
        CONFIRMED = "confirmed", "مؤكد"
        CANCELED = "canceled", "ملغي"

    class Meta:
        verbose_name = "موعد معاينة"
        verbose_name_plural = "مواعيد المعاينة"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["booking_date", "booking_time"]),
            models.Index(fields=["status"]),
        ]

    property = models.ForeignKey(
        "Property",
        verbose_name="العقار",
        on_delete=models.CASCADE,
        related_name="appointments",
    )
    client_name = models.CharField("اسم العميل", max_length=255)
    client_email = models.EmailField("البريد الإلكتروني", blank=True, null=True)
    client_phone = models.CharField("رقم الجوال", max_length=20)
    booking_date = models.DateField("تاريخ الموعد")
    booking_time = models.TimeField("وقت الموعد")
    status = models.CharField(
        "حالة الموعد",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    cancel_token = models.UUIDField(
        "رمز الإلغاء",
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("تاريخ التحديث", auto_now=True)

    def __str__(self):
        return f"{self.client_name} — {self.property.listing_id or self.property_id} ({self.booking_date} {self.booking_time})"


# =====================================================
# 🔔 CRM NOTIFICATION (تنبيهات النظام للمسوقين)
# =====================================================

class CRMNotification(models.Model):
    class Meta:
        verbose_name = "تنبيه CRM"
        verbose_name_plural = "تنبيهات CRM"
        ordering = ["-created_at"]

    user = models.ForeignKey(
        "auth.User", 
        verbose_name="المستخدم",
        on_delete=models.CASCADE, 
        related_name="crm_notifications"
    )
    title = models.CharField("العنوان", max_length=255)
    message = models.TextField("الرسالة")
    link = models.CharField("رابط الإجراء", max_length=500, null=True, blank=True)
    is_read = models.BooleanField("تمت القراءة", default=False)
    created_at = models.DateTimeField("تاريخ التنبيه", auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.user.username}"


# =====================================================
# شريط التنبيه المتحرك (أسفل الهيدر)
# =====================================================

class SiteTicker(models.Model):
    """إعدادات شريط الأخبار/التنبيه — سجل واحد يتحكم بالواجهة."""

    class Meta:
        verbose_name = "شريط التنبيه المتحرك"
        verbose_name_plural = "شريط التنبيه المتحرك"

    is_enabled = models.BooleanField(
        "إظهار الشريط",
        default=False,
        help_text="فعّل لإظهار الشريط أسفل الهيدر في الواجهة.",
    )
    label = models.CharField(
        "وسم الشريط",
        max_length=40,
        default="عاجل",
        blank=True,
        help_text="مثال: عاجل، تنبيه، فرصة",
    )
    message = models.CharField(
        "نص التنبيه",
        max_length=500,
        blank=True,
        default="",
        help_text="النص الذي يتحرك داخل الشريط.",
    )
    background_color = models.CharField(
        "لون الخلفية",
        max_length=7,
        default="#1B4F9C",
        help_text="بصيغة HEX مثل #1B4F9C",
    )
    text_color = models.CharField(
        "لون الخط",
        max_length=7,
        default="#FFFFFF",
        help_text="بصيغة HEX مثل #FFFFFF",
    )
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    def __str__(self):
        state = "مفعّل" if self.is_enabled else "مخفي"
        return f"شريط التنبيه ({state})"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


# =====================================================
# تواصل عام (نموذج تواصل معنا)
# =====================================================

class GeneralContact(models.Model):
    """رسائل نموذج «تواصل معنا» من الموقع."""

    class Meta:
        verbose_name = "رسالة تواصل"
        verbose_name_plural = "رسائل التواصل"
        ordering = ["-created_at"]

    name = models.CharField("الاسم", max_length=200)
    phone = models.CharField("الجوال", max_length=30)
    subject = models.TextField("تفاصيل الطلب", blank=True, default="")
    is_handled = models.BooleanField("تمت المتابعة", default=False)
    created_at = models.DateTimeField("تاريخ الإرسال", auto_now_add=True)

    def __str__(self):
        return f"{self.name} — {self.phone}"


# =====================================================
# بنر إعلاني وسط قائمة العروض
# =====================================================

class SiteAdBanner(models.Model):
    """بنر يظهر بعد عدد معيّن من كروت العروض — سجل واحد للإعدادات."""

    class Meta:
        verbose_name = "البنر الإعلاني"
        verbose_name_plural = "البنر الإعلاني"

    is_enabled = models.BooleanField(
        "إظهار البنر",
        default=True,
        help_text="فعّل لإظهار البنر داخل قائمة العروض العقارية.",
    )
    image = models.ImageField(
        "تصميم البنر",
        upload_to="ad_banners/",
        null=True,
        blank=True,
        help_text="ارفع تصميماً مناسباً للجوال والتابلت (مستحسن 1080×540 أو نسبة 2:1).",
    )
    link_url = models.URLField(
        "رابط عند الضغط",
        blank=True,
        default="",
        help_text="اختياري — يفتح عند الضغط على البنر.",
    )
    alt_text = models.CharField(
        "النص البديل",
        max_length=200,
        blank=True,
        default="الركن الأوسط للعقارات — تأجير · بيع · إدارة أملاك · تطوير عقاري",
    )
    insert_after = models.PositiveSmallIntegerField(
        "يظهر بعد كم عرض",
        default=3,
        help_text="مثال: 3 يعني بعد ثالث عقار في القائمة.",
    )
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    def __str__(self):
        state = "مفعّل" if self.is_enabled else "مخفي"
        return f"البنر الإعلاني ({state})"

    def save(self, *args, **kwargs):
        self.pk = 1
        if self.insert_after < 1:
            self.insert_after = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def has_custom_image(self):
        return bool(self.image)

    @property
    def image_url(self):
        if self.image:
            try:
                return self.image.url
            except Exception:
                pass
        return ""
