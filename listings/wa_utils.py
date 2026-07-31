import urllib.parse
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def post_property_to_whatsapp(property_obj, request):
    """
    Returns (True, intent_url) on success, (False, error_message) on failure.
    Generates a pre-filled WhatsApp link that the Admin can click to post.
    """
    try:
        import random
        from django.utils import timezone
        
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

        # 3. Define intros
        company_name = getattr(settings, 'COMPANY_NAME', 'جودة المستقبل')
        company_name_full = getattr(settings, 'COMPANY_NAME_FULL', 'جودة المستقبل للتطوير والاستثمار العقاري')
        
        intros = [
            f"🏠 عرض عقاري جديد ومميز من {company_name}!",
            "✨ فرصة استثمارية رائعة لا تفوتك!",
            f"🔑 عقارك المفضل الآن متاح عبر منصة {company_name}.",
            "🌟 نضع بين يديك هذا العرض الحصري، تواصل معنا الآن!",
            "🏢 هل تبحث عن عقار بهذه المواصفات؟ إليك هذا العرض:",
            f"💎 منتقى بعناية لأجلك! أحدث عروض {company_name}."
        ]
        chosen_intro = random.choice(intros)

        # 4. Gather amenities/details
        details = []
        if getattr(property_obj, 'property_age', None):
            details.append(f"العمر: {property_obj.property_age}")
        if getattr(property_obj, 'rooms', None):
            details.append(f"الغرف: {property_obj.rooms}")
        if getattr(property_obj, 'bathrooms', None):
            details.append(f"دورات المياه: {property_obj.bathrooms}")
            
        details_str = " | ".join(details) if details else ""

        # 6. Quick links (رابط العرض التفصيلي ورابط الطلبات السريعة/البطاقة الذكية)
        smart_link_url = f"{base_url}/link/"  # Assuming /link/ is the smart card link from earlier conversations

        # Construct Message
        message_parts = [
            f"*{chosen_intro}*\n",
            f"🔹 *{title}*",
            f"💰 *السعر:* {price_str}",
            f"📏 *المساحة:* {area}",
        ]
        
        if details_str:
            message_parts.append(f"📌 *المواصفات:* {details_str}")
            
        message_parts.extend([
            "",
            "🔗 *(لمشاهدة ألبوم الصور وتفاصيل العقار كاملة، تفضل بزيارة الرابط التالي 👇)*",
            url,
            "",
            "👇 *لطلباتكم واستفساراتكم السريعة:*",
            smart_link_url,
            "",
            f"✨ *{company_name_full}*"
        ])

        wa_text = "\n".join(message_parts)
        encoded_text = urllib.parse.quote(wa_text)
        intent_url = f"https://api.whatsapp.com/send?text={encoded_text}"
        
        return True, intent_url

    except Exception as e:
        logger.error(f"Error generating WhatsApp intent link: {e}")
        return False, f"حدث خطأ أثناء المعالجة: {str(e)}"
