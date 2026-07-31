import re
from decimal import Decimal

from rest_framework import serializers

from .models import Property, PropertyBooking, PropertyRequest
from .services.property_request_lead import (
    compute_lead_score_and_priority,
    sanitize_text_input,
)


class PropertySerializer(serializers.ModelSerializer):

    display_price = serializers.SerializerMethodField()

    image1 = serializers.SerializerMethodField()
    image2 = serializers.SerializerMethodField()
    image3 = serializers.SerializerMethodField()
    image4 = serializers.SerializerMethodField()
    image5 = serializers.SerializerMethodField()
    image6 = serializers.SerializerMethodField()
    image7 = serializers.SerializerMethodField()
    image8 = serializers.SerializerMethodField()
    image9 = serializers.SerializerMethodField()
    image10 = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = "__all__"  # سيضيف display_price تلقائياً

    # ==========================
    # 🔥 توحيد منطق عرض السعر
    # ==========================
    def get_display_price(self, obj):
        if obj.show_price_to_visitors and obj.price:
            return obj.price
        return None

    # ==========================
    # معالجة الصور
    # ==========================
    def _get_image_url(self, image):
        if not image:
            return None

        try:
            url = image.url
        except Exception:
            return None

        if url.startswith("http"):
            return url

        return None

    def get_image1(self, obj): return self._get_image_url(obj.image1)
    def get_image2(self, obj): return self._get_image_url(obj.image2)
    def get_image3(self, obj): return self._get_image_url(obj.image3)
    def get_image4(self, obj): return self._get_image_url(obj.image4)
    def get_image5(self, obj): return self._get_image_url(obj.image5)
    def get_image6(self, obj): return self._get_image_url(obj.image6)
    def get_image7(self, obj): return self._get_image_url(obj.image7)
    def get_image8(self, obj): return self._get_image_url(obj.image8)
    def get_image9(self, obj): return self._get_image_url(obj.image9)
    def get_image10(self, obj): return self._get_image_url(obj.image10)


# --- PropertyRequest unified API (website + AI chatbot) ---

# خرائط نوع العقار: إنجليزي (API) ↔ قيم Property.PROPERTY_TYPES (عربي في DB)
API_PROPERTY_TYPE_SLUGS = {
    "apartment": "شقة",
    "villa": "فيلا",
    "land": "أرض",
    "building": "عمارة",
    "palace": "قصر",
    "floor": "دور",
    "farm": "مزرعة",
    "rest_house": "استراحة",
    "shop": "محل تجاري",
}
_VALID_AR_TYPES = {c[0] for c in Property.PROPERTY_TYPES}


def normalize_saudi_phone_e164(phone: str) -> str:
    """Normalize to 9665XXXXXXXX for storage (matches existing PropertyRequest rows)."""
    p = re.sub(r"\D", "", (phone or "").strip())
    if p.startswith("00"):
        p = p[2:]
    if p.startswith("0") and len(p) == 10 and p.startswith("05"):
        p = "966" + p[1:]
    if p.startswith("966") and len(p) == 12 and p[3] == "5":
        return p
    raise serializers.ValidationError(
        "رقم جوال سعودي غير صالح. استخدم صيغة 05XXXXXXXX أو 9665XXXXXXXX."
    )


class PropertyRequestCreateSerializer(serializers.ModelSerializer):
    """
    POST /api/property-requests/ — JSON body.
    يقبل property_type كسلسلة إنجليزية (slug) أو القيمة العربية المخزّنة في النظام.
    """

    property_type = serializers.CharField(max_length=50)
    budget = serializers.DecimalField(max_digits=18, decimal_places=2)
    phone = serializers.CharField(max_length=20)
    source = serializers.ChoiceField(choices=PropertyRequest.SOURCE_CHOICES, default="website")
    rooms = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=50)
    furnished = serializers.BooleanField(required=False, allow_null=True)
    # افتراض عائلي يُسهّل تكامل n8n والبوتات دون حقل إضافي
    category = serializers.ChoiceField(
        choices=PropertyRequest.HOUSEHOLD_CATEGORY_CHOICES,
        required=False,
        default="family",
    )
    notes = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    conversation_id = serializers.CharField(required=False, allow_blank=True, max_length=128)

    class Meta:
        model = PropertyRequest
        fields = (
            "name",
            "phone",
            "property_type",
            "district",
            "budget",
            "rooms",
            "furnished",
            "category",
            "notes",
            "source",
            "conversation_id",
        )

    def validate_name(self, value: str) -> str:
        v = sanitize_text_input(value, max_length=255)
        if not v:
            raise serializers.ValidationError("الاسم مطلوب.")
        return v

    def validate_district(self, value: str) -> str:
        v = sanitize_text_input(value, max_length=100)
        if not v:
            raise serializers.ValidationError("الحي مطلوب.")
        return v

    def validate_phone(self, value: str) -> str:
        return normalize_saudi_phone_e164(value)

    def validate_property_type(self, value: str) -> str:
        v = (value or "").strip()
        if not v:
            raise serializers.ValidationError("نوع العقار مطلوب.")
        key = v.lower().replace(" ", "_")
        if key in API_PROPERTY_TYPE_SLUGS:
            return API_PROPERTY_TYPE_SLUGS[key]
        if v in _VALID_AR_TYPES:
            return v
        raise serializers.ValidationError(
            "نوع عقار غير مدعوم. استخدم slugs مثل apartment, villa, land أو القيم العربية المعتمدة."
        )

    def validate_budget(self, value: Decimal) -> Decimal:
        if value is None:
            raise serializers.ValidationError("الميزانية مطلوبة.")
        if value <= 0:
            raise serializers.ValidationError("الميزانية يجب أن تكون أكبر من صفر.")
        return value

    def validate_notes(self, value):
        if value in (None, ""):
            return ""
        return sanitize_text_input(value, max_length=4000)

    def validate_conversation_id(self, value):
        if value in (None, ""):
            return ""
        return sanitize_text_input(value, max_length=128)

    def create(self, validated_data):
        rooms = validated_data.get("rooms")
        extra = {}
        if rooms is not None:
            extra["rooms_count"] = str(rooms)

        lead_score, priority = compute_lead_score_and_priority(
            budget=validated_data.get("budget"),
            district=validated_data["district"],
            rooms=validated_data.get("rooms"),
            furnished=validated_data.get("furnished"),
            category=validated_data.get("category"),
            notes=validated_data.get("notes") or "",
            conversation_id=validated_data.get("conversation_id") or "",
            name=validated_data["name"],
        )
        extra["score"] = lead_score
        extra["priority"] = priority

        return PropertyRequest.objects.create(
            status="new",
            client_segment="search",
            **validated_data,
            **extra,
        )


class PropertyBookingSerializer(serializers.ModelSerializer):
    """
    Serializer to receive booking/viewing requests.
    """
    listing_id = serializers.CharField(write_only=True)

    class Meta:
        model = PropertyBooking
        fields = ['name', 'phone', 'booking_date', 'booking_time', 'notes', 'listing_id']

    def validate_listing_id(self, value):
        if not Property.objects.filter(listing_id=value).exists():
            raise serializers.ValidationError("رقم العقار غير موجود.")
        return value

    def create(self, validated_data):
        listing_id = validated_data.pop('listing_id')
        property_obj = Property.objects.get(listing_id=listing_id)
        return PropertyBooking.objects.create(property=property_obj, **validated_data)


class FlatPropertySerializer(serializers.ModelSerializer):
    """
    Serializer optimized for AI and n8n (Google Sheets style).
    Flattens images and provides a combined description.
    """
    display_price = serializers.SerializerMethodField()
    flat_description = serializers.SerializerMethodField()
    
    # Images as absolute URLs
    image1 = serializers.SerializerMethodField()
    image2 = serializers.SerializerMethodField()
    image3 = serializers.SerializerMethodField()
    image4 = serializers.SerializerMethodField()
    image5 = serializers.SerializerMethodField()
    image6 = serializers.SerializerMethodField()
    image7 = serializers.SerializerMethodField()
    image8 = serializers.SerializerMethodField()
    image9 = serializers.SerializerMethodField()
    image10 = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = [
            'id', 'listing_id', 'full_name', 'phone', 'city', 'district',
            'property_type', 'offer_type', 'category', 'area', 'price',
            'display_price', 'status', 'created_at', 'flat_description',
            'property_age', 'floors', 'rooms', 'apartments', 'bathrooms',
            'image1', 'image2', 'image3', 'image4', 'image5',
            'image6', 'image7', 'image8', 'image9', 'image10',
            'map_url', 'video_url'
        ]

    def get_display_price(self, obj):
        return float(obj.price) if obj.price else 0

    def get_flat_description(self, obj):
        return (
            f"عقار {obj.property_type} لـ {obj.offer_type} في {obj.city}، حي {obj.district or 'غير محدد'}. "
            f"المساحة {obj.area} م2. السعر {obj.price} ريال. "
            f"التفاصيل: {obj.owner_notes or 'لا يوجد ملاحظات إضافية'}."
        )

    def _get_image_url(self, image):
        if not image:
            return ""
        try:
            return image.url
        except:
            return ""

    def get_image1(self, obj): return self._get_image_url(obj.image1)
    def get_image2(self, obj): return self._get_image_url(obj.image2)
    def get_image3(self, obj): return self._get_image_url(obj.image3)
    def get_image4(self, obj): return self._get_image_url(obj.image4)
    def get_image5(self, obj): return self._get_image_url(obj.image5)
    def get_image6(self, obj): return self._get_image_url(obj.image6)
    def get_image7(self, obj): return self._get_image_url(obj.image7)
    def get_image8(self, obj): return self._get_image_url(obj.image8)
    def get_image9(self, obj): return self._get_image_url(obj.image9)
    def get_image10(self, obj): return self._get_image_url(obj.image10)