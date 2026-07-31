# -*- coding: utf-8 -*-
"""حقول وسائط تدعم التخزين المحلي أو Cloudinary حسب الإعدادات."""
from django.conf import settings
from django.db import models


def media_image_field(verbose_name, upload_to="property_images/", **kwargs):
    """
    ImageField عادي — الوجهة تُحدد عبر STORAGES في settings:
    - Cloudinary إن وُجدت المفاتيح
    - الملفات المحلية media/ إن لم توجد
    """
    defaults = {
        "verbose_name": verbose_name,
        "upload_to": upload_to,
        "null": True,
        "blank": True,
        "max_length": 2000,
    }
    defaults.update(kwargs)
    return models.ImageField(**defaults)


USE_CLOUDINARY = bool(
    getattr(settings, "USE_CLOUDINARY", False)
    or (
        getattr(settings, "CLOUDINARY_STORAGE", {}).get("CLOUD_NAME")
        and getattr(settings, "CLOUDINARY_STORAGE", {}).get("API_KEY")
        and getattr(settings, "CLOUDINARY_STORAGE", {}).get("API_SECRET")
    )
)
