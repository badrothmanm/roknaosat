from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def generate_property_copy_text(property_obj, request):
    """
    Returns (True, text) on success, (False, error_message) on failure.
    Generates a pre-formatted text suitable for copying to platforms like Haraj.
    """
    try:
        company_name_full = getattr(settings, 'COMPANY_NAME_FULL', 'جودة المستقبل للتطوير والاستثمار العقاري')
        
        # 1. Prepare Title and Offer Type
        offer_type = getattr(property_obj, 'offer_type', '')
        offer_prefix = "للبيع" if offer_type == 'بيع' else "للإيجار" if offer_type == 'إيجار' else ""
        title = f"{property_obj.property_type} {offer_prefix} في حي {property_obj.district}".replace("  ", " ")

        # 2. Prepare Price based on visibility and status
        nego_status = getattr(property_obj, 'negotiation_status', None)
        nego_text = f" ({nego_status})" if nego_status else ""
        
        if not getattr(property_obj, 'show_price_to_visitors', True):
            price_str = f"على السوم أو عند التواصل{nego_text}"
        else:
            price_val = getattr(property_obj, 'price', 0)
            price_str = f"{price_val:,} ريال{nego_text}" if price_val else f"غير محدد{nego_text}"
            
        area = f"{property_obj.area} م²"
        base_url = request.build_absolute_uri('/').rstrip('/')
        url = f"{base_url}/property/{property_obj.pk}/"

        # 3. Gather amenities/details
        details = []
        if getattr(property_obj, 'property_age', None):
            details.append(f"العمر: {property_obj.property_age}")
        if getattr(property_obj, 'rooms', None):
            details.append(f"الغرف: {property_obj.rooms}")
        if getattr(property_obj, 'bathrooms', None):
            details.append(f"دورات المياه: {property_obj.bathrooms}")
        if getattr(property_obj, 'floors', None):
            details.append(f"الأدوار: {property_obj.floors}")
        if getattr(property_obj, 'apartments', None):
            details.append(f"الشقق: {property_obj.apartments}")
            
        # 4. Construct Message
        message_parts = [
            f"🔹 {title} 🔹",
            "",
            "📌 تفاصيل العقار:",
            f"▪️ السعر: {price_str}",
            f"▪️ المساحة: {area}",
            f"▪️ المدينة: {getattr(property_obj, 'city', '')}",
            f"▪️ الحي: {getattr(property_obj, 'district', '')}",
        ]
        
        if details:
            for detail in details:
                message_parts.append(f"▪️ {detail}")
                
        # 5. Owner/Admin Notes (Public description)
        notes = getattr(property_obj, 'owner_notes', '')
        if notes:
            message_parts.extend([
                "",
                "📝 تفاصيل إضافية:",
                notes
            ])
            
        message_parts.extend([
            "",
            "🔗 لمشاهدة الصور التفصيلية والفيديو عبر منصتنا:",
            url,
            "",
            f"✨ {company_name_full} ✨",
            "نسعى دائماً لتقديم الأفضل."
        ])

        copy_text = "\n".join(message_parts)
        
        return True, copy_text

    except Exception as e:
        logger.error(f"Error generating copy text: {e}")
        return False, f"حدث خطأ أثناء المعالجة: {str(e)}"
