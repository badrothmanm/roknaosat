import urllib.parse
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def post_property_to_x(property_obj, request=None):
    """
    Returns (True, intent_url) on success, (False, error_message) on failure.
    Instead of calling the API (which requires paid credits), this generates
    a pre-filled X (Twitter) intent link that the Admin can click to post.
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
            price_str = f"السعر: على السوم أو عند التواصل{nego_text}"
        else:
            price_val = getattr(property_obj, 'price', 0)
            price_str = f"السعر: {price_val:,} ريال{nego_text}" if price_val else f"السعر: غير محدد{nego_text}"
        area = f"المساحة: {property_obj.area} م²"
        url = f"https://jodah.onrender.com/property/{property_obj.pk}/"
        time_str = timezone.localtime().strftime("%I:%M %p")

        # 3. Define 6 distinct intros
        intros = [
            "🏠 عرض عقاري جديد ومميز من جودة المستقبل!",
            "✨ فرصة استثمارية رائعة لا تفوتك!",
            "🔑 عقارك المفضل الآن متاح عبر منصة جودة المستقبل.",
            "🌟 نضع بين يديك هذا العرض الحصري، تواصل معنا الآن!",
            "🏢 هل تبحث عن عقار بهذا المواصفات؟ إليك هذا العرض:",
            "💎 منتقى بعناية لأجلك! أحدث عروض جودة المستقبل العقارية."
        ]
        chosen_intro = random.choice(intros)

        # 4. Construct Tweet
        tweet_text = f"{chosen_intro}\n\n🔹 {title}\n💰 {price_str}\n📏 {area}\n\n📍 لمزيد من التفاصيل:\n{url}\n\n#عقارات_جدة #جودة_المستقبل #عقارات\n🕒 {time_str}"

        # URL encode the tweet text
        encoded_text = urllib.parse.quote(tweet_text)
        intent_url = f"https://twitter.com/intent/tweet?text={encoded_text}"
        
        return True, intent_url

    except Exception as e:
        logger.error(f"Error generating X intent link: {e}")
        return False, f"حدث خطأ أثناء المعالجة: {str(e)}"
