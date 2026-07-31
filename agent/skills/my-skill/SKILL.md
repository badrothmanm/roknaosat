name: nano-banana-landing-image  
description: توليد تصميم صورة/هيرو لصفحة الهبوط (Landing Page Hero Image) باستخدام Google AI Studio عبر Gemini Image Preview. استخدمها عندما تحتاج صورة # nano-banana landing image (Google AI Studio)
جاهزة للاستخدام في صفحة هبوط (Hero / Banner / Section image) مع نص إرشادي بديل (Alt text) وإرشادات ستايل.

---

## My Skill

هذه المهارة تنشئ صورًا عالية الجودة لصفحات الهبوط عبر استدعاء Google Generative Language API باستخدام نموذج الصور (مثال: `gemini-3-pro-image-preview`) و endpoint `streamGenerateContent`.  
تُرجع المخرجات عادةً:
- **IMAGE** (بيانات الصورة)
- **TEXT** (وصف مختصر + alt text + اقتراحات تحسين)

---

## When to use this skill

استخدم هذه المهارة عندما:
- تحتاج **Hero image** لصفحة هبوط لمنتج/خدمة SaaS.
- تريد **تصميم بصري موحّد** مع هوية (ألوان/ستايل/إضاءة/خلفية) بدون مصمم.
- تحتاج **عدة Variations** بسرعة (A/B testing).
- تريد صور Sections مثل: features, pricing, testimonials, dashboard mock scene.

---

## This is helpful for

- مواقع SaaS والمنتجات الرقمية.
- صفحات إطلاق منتج (Launch) وإعلانات.
- بناء مكتبة صور متناسقة للبراند.
- توليد صور بخلفية شفافة أو خلفيات مناسبة للويب (حسب إمكانيات النموذج).

---

## Inputs (What you must provide)

قبل الاستدعاء، جهّز Prompt منظم يحتوي على:
1) **هدف الصورة**: (Hero / Feature / Background)
2) **موضوع الصورة**: (مثال: لوحة تحكم، شخصية، جهاز، عنصر رمزي)
3) **الأسلوب**: (minimal, 3D, flat, photoreal, gradient, glassmorphism…)
4) **الألوان**: (primary/secondary + hex إن توفر)
5) **المقاس المقترح**: (مثال 1024/1K، أو نسبة 16:9 للهيرو)
6) **قيود**: (بدون نص داخل الصورة، أو نص محدود، أو بدون وجوه…)
7) **مخرجات نصية**: alt text + وصف مختصر + 3 تحسينات مقترحة

---

## Security & Safety rules

- لا تضع مفتاح API داخل الكود أو ملفات repo. استخدم متغير بيئة: `GEMINI_API_KEY`.
- لا تمرر بيانات حساسة (مفاتيح، رموز، معلومات عملاء) في الـ prompt.
- استخدم HTTPS فقط (الـ endpoint الرسمي يستخدم HTTPS).
- تحقّق من إدخال المستخدم (sanitize) إذا كان prompt يتكوّن من مدخلات UI لمنع الحقن النصي أو المحتوى غير المرغوب.

---

## Error handling rules

- إذا فشل الطلب:
  - اطبع HTTP status و body (إن أمكن) لكن **لا تطبع API key**.
  - أعد المحاولة مع backoff بسيط عند 429/503.
- إذا كانت الاستجابة streaming:
  - اجمع chunks بأمان.
  - تعامل مع JSON parse errors بشكل واضح.
- إذا لم تُرجع IMAGE:
  - أعد الطلب مع prompt مبسط + تأكيد `responseModalities` تحتوي IMAGE.

---

## Performance rules

- استخدم حجم صورة مناسب للويب (1K غالبًا كافٍ للهيرو كبداية).
- لا تنشئ 10 صور دفعة واحدة إلا عند الحاجة—ابدأ بـ 2-3 variations.
- خزّن النتائج محليًا/على CDN بدل تكرار التوليد.

---

## How to use it (Step-by-step)

### 1) المتطلبات
- لديك `GEMINI_API_KEY` في البيئة:
  - Linux/macOS:
    - `export GEMINI_API_KEY="YOUR_KEY"`
  - CI:
    - ضعها في Secrets

### 2) كوّن Prompt احترافي لصفحة هبوط
**قالب Prompt مقترح (Hero):**
- Product: <اسم المنتج + فائدته>
- Audience: <لمن؟>
- Visual metaphor: <فكرة بصرية: dashboard floating cards / rocket / flow diagram…>
- Style: <minimal 3D, soft shadows, gradient background, glassmorphism>
- Color palette: <hex codes>
- Composition: <center-left empty space for headline, subject right>
- Constraints: “no text in image”, “clean”, “web hero”
- Output: “also return alt text and 3 variant ideas”

### 3) أنشئ request.json
- ضع `contents[0].parts[0].text` = prompt النهائي.
- فعّل modalities: `["IMAGE","TEXT"]`
- image size: `"1K"`

### 4) نفّذ الاستدعاء (curl)
- استعمل endpoint:
`https://generativelanguage.googleapis.com/v1beta/models/${MODEL_ID}:${GENERATE_CONTENT_API}?key=${GEMINI_API_KEY}`

### 5) حفظ الصورة
- استخرج بيانات الصورة من الاستجابة (عادة Base64 أو inline data حسب streaming format)
- احفظها كـ PNG/WebP
- خزّن معها ملف نصي: alt/description

---

## Canonical Bash example (based on Google AI Studio)

```bash
#!/bin/bash
set -e -E

: "${GEMINI_API_KEY:?Missing GEMINI_API_KEY}"

MODEL_ID="gemini-3-pro-image-preview"
GENERATE_CONTENT_API="streamGenerateContent"

PROMPT="Create a modern landing page hero image for a SaaS product. Minimal 3D style, soft gradient background, floating dashboard cards, lots of empty space on the left for headline, no text in the image. Return alt text and 3 variant ideas."

cat > request.json <<EOF
{
  "contents": [
    {
      "role": "user",
      "parts": [
        { "text": "${PROMPT}" }
      ]
    }
  ],
  "generationConfig": {
    "responseModalities": ["IMAGE", "TEXT"],
    "imageConfig": { "image_size": "1K" }
  }
}
EOF

curl -sS \
  -X POST \
  -H "Content-Type: application/json" \
  "https://generativelanguage.googleapis.com/v1beta/models/${MODEL_ID}:${GENERATE_CONTENT_API}?key=${GEMINI_API_KEY}" \
  -d '@request.json' \
  | tee response.json