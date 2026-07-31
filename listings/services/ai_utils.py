from google import genai
import os
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

def _get_client():
    """مورد مشترك لعميل Gemini."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None, "GEMINI_API_KEY غير مهيأ في النظام."
    try:
        client = genai.Client(api_key=api_key)
        return client, None
    except Exception as e:
        logger.error(f"Gemini client init: {e}")
        return None, str(e)

def _generate(prompt, max_output_tokens=1024):
    """تنفيذ الطلب وإرجاع (True, text) أو (False, error_message)."""
    client, err = _get_client()
    if err:
        return False, err
    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt
        )
        if response and response.text:
            return True, response.text.strip()
        return False, "لم يُرجع النموذج نصاً."
    except Exception as e:
        logger.error(f"Gemini API Error: {e}")
        return False, f"حدث خطأ أثناء الاتصال بـ Gemini: {str(e)}"

def generate_creative_description(property_obj):
    """
    يولد وصفاً تسويقياً إبداعياً للعقار للنشر على وسائل التواصل (الاستخدام الحالي).
    """
    specs = []
    if property_obj.area:
        specs.append(f"مساحة: {property_obj.area} م²")
    if property_obj.rooms:
        specs.append(f"غرف: {property_obj.rooms}")
    if property_obj.bathrooms:
        specs.append(f"دورات مياه: {property_obj.bathrooms}")
    if property_obj.floors:
        specs.append(f"أدوار: {property_obj.floors}")
    if property_obj.property_age:
        specs.append(f"عمر العقار: {property_obj.property_age}")
    specs_str = "، ".join(specs) if specs else "—"

    offer_display = getattr(property_obj, "offer_type", "") or ""
    if hasattr(property_obj, "get_offer_type_display"):
        try:
            offer_display = property_obj.get_offer_type_display()
        except Exception:
            pass

    prompt = f"""
أنت خبير تسويق عقاري في المملكة العربية السعودية (شركة جودة المستقبل).
اكتب وصفاً إبداعياً وجذاباً لعقار بالمواصفات التالية:
- نوع العقار: {property_obj.property_type}
- نوع العرض: {offer_display}
- الحي: {getattr(property_obj, 'district', '')}
- المدينة: {getattr(property_obj, 'city', '')}
- السعر: {property_obj.price:,.0f} ريال
- المواصفات: {specs_str}

المطلوب: نص تسويقي يصلح لسناب وتويتر وإنستقرام، بإيموجي مناسبة، لغة عربية راقية، دون أرقام جوال أو روابط. ابدأ مباشرة بالنص الإعلاني.
"""
    return _generate(prompt)


# ─── استعمالات إضافية لربط Gemini ───

def generate_property_meta_seo(property_obj):
    """
    يولد عنواناً (أقل من 60 حرفاً) ووصفاً meta (أقل من 160 حرفاً) لتحسين محركات البحث ومعاينة الروابط.
    الإرجاع: (True, {"title": "...", "description": "..."}) أو (False, error_message).
    """
    prompt = f"""
من عقار: {property_obj.property_type}، {getattr(property_obj, 'district', '')}، {getattr(property_obj, 'city', '')}، سعر {property_obj.price:,.0f} ريال.
أعطِ سطرين فقط بالضبط:
السطر الأول: عنوان مناسب لـ SEO (أقل من 60 حرفاً عربي)، يصلح كـ title و og:title.
السطر الثاني: وصف مختصر للمعاينة (أقل من 160 حرفاً)، يصلح كـ meta description و og:description.
لا عناوين فرعية، فقط السطرين.
"""
    ok, text = _generate(prompt, max_output_tokens=256)
    if not ok:
        return False, text
    lines = [ln.strip() for ln in text.strip().split("\n") if ln.strip()]
    title = lines[0][:60] if lines else ""
    description = (lines[1] if len(lines) > 1 else lines[0])[:160]
    return True, {"title": title, "description": description}


def generate_whatsapp_short(property_obj, max_chars=400):
    """
    نسخة قصيرة من الوصف الإبداعي مناسبة لرسالة واتساب (حد أحرف تقريبي).
    الإرجاع: (True, text) أو (False, error_message).
    """
    prompt = f"""
عقار: {property_obj.property_type}، حي {getattr(property_obj, 'district', '')}، {getattr(property_obj, 'city', '')}، سعر {property_obj.price:,.0f} ريال.
اكتب رسالة واتساب واحدة قصيرة جداً (أقل من {max_chars} حرف)، جذابة، مع إيموجي قليلة، مناسبة للنسخ في واتساب. بدون روابط أو أرقام. عربي فصيح.
"""
    return _generate(prompt, max_output_tokens=256)


def generate_hashtags(property_obj, count=8):
    """
    يقترح هاشتاقات مناسبة للعقار لإنستغرام وتويتر.
    الإرجاع: (True, " #هاشتاق1 #هاشتاق2 ...") أو (False, error_message).
    """
    prompt = f"""
عقار للعرض: {property_obj.property_type}، {getattr(property_obj, 'offer_type', '')}، حي {getattr(property_obj, 'district', '')}، جدة.
أعطِ {count} هاشتاقات عربية وإنجليزية مناسبة لإنستغرام وتويتر (عقارات، جدة، بيع، إيجار). صيغة سطر واحد: #هاشتاق1 #هاشتاق2 ...
"""
    return _generate(prompt, max_output_tokens=128)


def generate_reply_to_inquiry(property_title_or_id, inquiry_text):
    """
    يقترح رداً احترافياً قصيراً على استفسار عميل عن عقار.
    property_title_or_id: عنوان العقار أو رقمه. inquiry_text: نص رسالة العميل.
    الإرجاع: (True, reply_text) أو (False, error_message).
    """
    prompt = f"""
عميل استفسر عن عقار: "{property_title_or_id}".
نص استفساره: "{inquiry_text[:500]}".
اكتب رداً احترافياً قصيراً (2–4 جمل) من شركة عقارية، ودود، يدعو للتواصل ويشكر العميل. بدون أرقام جوال. عربي.
"""
    return _generate(prompt, max_output_tokens=256)


def generate_request_brief(property_request):
    """
    يلخص طلب العميل (PropertyRequest) في جملة واحدة للمسوّق.
    الإرجاع: (True, "عميل يبحث عن فيلا في النسيم بميزانية 2 مليون") أو (False, error_message).
    """
    req = property_request
    budget = f"{req.budget:,.0f}" if getattr(req, "budget", None) else "غير محدد"
    prompt = f"""
طلب عقار: اسم {getattr(req, 'name', '')}، نوع عقار {getattr(req, 'property_type', '')}، حي {getattr(req, 'district', '')}، ميزانية {budget} ريال.
اكتب جملة واحدة فقط (تلخيص للمسوّق): "عميل يبحث عن [نوع] في [حي] بميزانية [X]".
"""
    return _generate(prompt, max_output_tokens=128)
def generate_offer_summary(offer_obj):
    """
    يولد ملخصاً تنفيذيًا لطلب تسويق عقاري مقدم من مالك (PropertyOffer).
    """
    data = [
        f"المناسبة: {offer_obj.get_status_display()}",
        f"المالك: {offer_obj.owner_name}",
        f"نوع العقار: {offer_obj.property_type}",
        f"المدينة/الحي: {offer_obj.city} - {offer_obj.neighborhood}",
        f"المساحة: {offer_obj.area}",
        f"السعر: {offer_obj.price}",
        f"المواصفات: غرف {offer_obj.rooms}، حمامات {offer_obj.bathrooms}، أدوار {offer_obj.floors}",
        f"ملاحظات: {offer_obj.owner_notes or 'لا يوجد'}"
    ]
    data_str = "\n".join(data)

    prompt = f"""
بصفتك مساعداً ذكياً لشركة "جودة المستقبل العقارية"، لخص هذا الطلب المقدم من مالك عقار في 3-4 نقاط مركزة جداً للمسوق.
ركز على الجوانب البيعية والفرص المتاحة في هذا العقار وكيفية الرد على المالك.

تفاصيل الطلب:
{data_str}

المطلوب: ملخص تنفيذي بالعربي، لغة مهنية ونشطة، بأسلوب النقاط.
"""
    return _generate(prompt)
