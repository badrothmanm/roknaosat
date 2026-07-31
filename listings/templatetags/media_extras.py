from __future__ import annotations

import urllib.parse

from django import template
from django.conf import settings


register = template.Library()


def _get_public_id(img) -> str | None:
    if img is None:
        return None
    pid = getattr(img, "public_id", None)
    if pid:
        return str(pid)
    # CloudinaryField قد يعيد str بالفعل
    if isinstance(img, str):
        s = img.strip()
        if not s:
            return None
        # إذا كان رابطاً كاملاً فلا نعامله كـ public_id
        if s.startswith("http://") or s.startswith("https://"):
            return None
        return s
    # كاحتياط: بعض كائنات CloudinaryField تُحوَّل لنص يمثل public_id
    try:
        s = str(img).strip()
        if s and s != "None":
            if s.startswith("http://") or s.startswith("https://"):
                return None
            return s
    except Exception:
        pass
    return None


@register.filter(name="wm")
def watermarked_url(img) -> str:
    """
    يرجع رابط صورة بعلامة مائية أنيقة (غير مزعجة) عبر Cloudinary transformations.
    إذا تعذر تحديد public_id أو Cloudinary غير متاح → يرجع img.url (إن وجد).
    """
    # يمكن تعطيل العلامة المائية عبر ENV: WATERMARK_ENABLED=False
    enabled = getattr(settings, "WATERMARK_ENABLED", True)
    if not enabled:
        return getattr(img, "url", "") or ""

    src_url = getattr(img, "url", "") or ""
    if not src_url:
        return ""
    # إذا لم تكن صورة Cloudinary (أو صيغة غير متوقعة) نعيد الرابط كما هو
    if "/upload/" not in src_url or "res.cloudinary.com" not in src_url:
        return src_url

    text = (getattr(settings, "WATERMARK_TEXT", None) or getattr(settings, "COMPANY_NAME", None) or "jodah.sa").strip()
    # ملاحظة: بعض الخطوط قد لا تكون مفعّلة في حساب Cloudinary
    font = getattr(settings, "WATERMARK_FONT_FAMILY", "Arial")
    font_size = int(getattr(settings, "WATERMARK_FONT_SIZE", 34) or 34)
    opacity = int(getattr(settings, "WATERMARK_OPACITY", 22) or 22)  # 0..100
    color = getattr(settings, "WATERMARK_COLOR", "ffffff")
    gravity = getattr(settings, "WATERMARK_GRAVITY", "south_east")
    x = int(getattr(settings, "WATERMARK_X", 24) or 24)
    y = int(getattr(settings, "WATERMARK_Y", 24) or 24)

    # نبني transformation ونحقنه داخل رابط Cloudinary الأصلي لضمان عدم كسر الصور.
    # Cloudinary URL transformation segment format:
    #   /upload/<TRANSFORMATION>/<public_id>
    encoded_text = urllib.parse.quote(text, safe="")
    # نستخدم l_text (الصيغة القياسية داخل رابط Cloudinary)
    t = (
        "f_auto,q_auto/"
        f"l_text:{font}_{font_size}:{encoded_text},"
        f"co_rgb:{color},o_{opacity},g_{gravity},x_{x},y_{y}/"
        "fl_layer_apply"
    )

    head, tail = src_url.split("/upload/", 1)
    # إذا كان هناك transformation موجود أصلاً (يبدأ غالباً بحرف/أو v123)
    # نضيف علامتنا في البداية بدون لمس باقي الرابط.
    return f"{head}/upload/{t}/{tail}"

