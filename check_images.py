import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from listings.models import Property

# أول عقار يحتوي على صور
p = Property.objects.filter(image1__isnull=False).first()

if not p:
    print("❌ لا يوجد أي عقار يحتوي على صور في قاعدة البيانات!")
else:
    print(f"✅ العقار: {p} (pk={p.pk})")
    print(f"   URL صفحة التفاصيل: /property/{p.pk}/")
    
    imgs = p.all_images
    print(f"\n📸 عدد الصور: {len(imgs)}")
    
    for i, img in enumerate(imgs):
        t = type(img).__name__
        url = getattr(img, 'url', 'NO URL ATTR')
        s = str(img)[:100]
        print(f"  صورة {i+1}: type={t}")
        print(f"    str()  = {s}")
        print(f"    .url   = {url}")
        print()

    # فحص صورة image1 مباشرة
    print("\n--- فحص image1 مباشرة ---")
    img1 = p.image1
    print(f"  type: {type(img1).__name__}")
    print(f"  str:  {str(img1)[:100]}")
    try:
        print(f"  url:  {img1.url}")
    except Exception as e:
        print(f"  url ERROR: {e}")

print("\n--- إعدادات Cloudinary ---")
from django.conf import settings
print(f"  CLOUDINARY_URL: {getattr(settings, 'CLOUDINARY_URL', 'NOT SET')[:50] if getattr(settings, 'CLOUDINARY_URL', None) else 'NOT SET'}")
print(f"  DEFAULT_FILE_STORAGE: {getattr(settings, 'DEFAULT_FILE_STORAGE', 'NOT SET')}")
