"""
Django settings for core project.
Production-ready configuration for Render + PostgreSQL.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import cloudinary

# =====================================================
# BASE
# =====================================================

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv()

# =====================================================
# SECURITY
# =====================================================

SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is not set.")

DEBUG = os.getenv("DEBUG", "False").lower() == "true"

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "jodah.onrender.com",
    "jodah.sa",
    "www.jodah.sa",
    ".onrender.com",
]

# رابط الموقع العلني (روابط الأدمن، البروشور، المشاركة). على Render: اضبط PUBLIC_SITE_URL لنطاقك الفعلي.
# تحذير: jodah.site قد لا يكون مسجّلاً في DNS — الافتراضي يشير إلى استضافة Render.
PUBLIC_SITE_URL = os.getenv("PUBLIC_SITE_URL", "https://jodah.onrender.com").rstrip("/")

# =====================================================
# EMAIL — تنبيهات أحداث العملاء (طلب، عرض، استفسار، طلب سريع، تعيين، إلخ)
# =====================================================
# محلياً: الافتراضي يطبع البريد في الطرفية (console).
# للإنتاج: اضبط SMTP (مثلاً Outlook/Hotmail أو مزود بريد) عبر متغيرات البيئة.
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Jodah CRM <noreply@jodah.sa>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

STAFF_EMAIL_NOTIFY_ENABLED = os.getenv("STAFF_EMAIL_NOTIFY_ENABLED", "true").lower() == "true"
STAFF_ACTION_NOTIFY_EMAILS = [
    addr.strip()
    for addr in os.getenv(
        "STAFF_ACTION_NOTIFY_EMAILS",
        "badr_othman@hotmail.com",
    ).split(",")
    if addr.strip()
]

# =====================================================
# APPLICATIONS
# =====================================================

INSTALLED_APPS = [
    # Admin System Theme (Must be before django.contrib.admin)
    "jazzmin",

    # Django Core
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.sitemaps",
    
    # --- المكتبة المضافة لحل مشكلة السعر ---
    "django.contrib.humanize", 

    # Third Party
    "rest_framework",
    "corsheaders",
    "cloudinary",
    "cloudinary_storage",

    # Local
    "listings.apps.ListingsConfig",
    "market",  # تم إضافة تطبيق البورصة العقارية هنا
    "apps.publishing.apps.PublishingConfig",
]

SITE_ID = 1

# =====================================================
# MIDDLEWARE
# =====================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "core.middleware.ApiCsrfJsonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.ApiJsonErrorMiddleware",
    "core.middleware.StaffAdminPasswordGateMiddleware",
    "core.middleware.MarketerAdminHomeRedirectMiddleware",
    "core.middleware.ImpersonationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.DateAccessMiddleware",
    "core.middleware.MarketerTrackingMiddleware",
]

ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"

# =====================================================
# TEMPLATES
# =====================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.debug",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "listings.context_processors.global_vars",
            ],
        },
    },
]

# =====================================================
# DATABASE
# =====================================================

if os.getenv("DB_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT", "5432"),
            "CONN_MAX_AGE": 600,
            "OPTIONS": {
                "sslmode": "require",
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# =====================================================
# PASSWORD VALIDATION
# =====================================================

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# =====================================================
# INTERNATIONALIZATION
# =====================================================

LANGUAGE_CODE = "ar"
TIME_ZONE = "Asia/Riyadh"

USE_I18N = True
USE_TZ = True

# =====================================================
# STATIC FILES
# =====================================================

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# =====================================================
# CLOUDINARY (اختياري — بدون مفاتيح يُستخدم التخزين المحلي)
# =====================================================

CLOUDINARY_STORAGE = {
    "CLOUD_NAME": os.getenv("CLOUDINARY_CLOUD_NAME") or "",
    "API_KEY": os.getenv("CLOUDINARY_API_KEY") or "",
    "API_SECRET": os.getenv("CLOUDINARY_API_SECRET") or "",
}

USE_CLOUDINARY = bool(
    CLOUDINARY_STORAGE["CLOUD_NAME"]
    and CLOUDINARY_STORAGE["API_KEY"]
    and CLOUDINARY_STORAGE["API_SECRET"]
)

if USE_CLOUDINARY:
    cloudinary.config(
        cloud_name=CLOUDINARY_STORAGE["CLOUD_NAME"],
        api_key=CLOUDINARY_STORAGE["API_KEY"],
        api_secret=CLOUDINARY_STORAGE["API_SECRET"],
        secure=True,
    )
    _DEFAULT_STORAGE = "cloudinary_storage.storage.MediaCloudinaryStorage"
else:
    _DEFAULT_STORAGE = "django.core.files.storage.FileSystemStorage"

STORAGES = {
    "default": {
        "BACKEND": _DEFAULT_STORAGE,
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# =====================================================
# GOOGLE GEN AI (Gemini)
# =====================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# =====================================================
# GOOGLE SHEETS
# =====================================================

APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL")
APPS_SCRIPT_KEY = os.getenv("APPS_SCRIPT_KEY")

GSHEETS_SPREADSHEET_ID = os.getenv("GSHEETS_SPREADSHEET_ID")
GSHEETS_SERVICE_ACCOUNT_FILE = os.getenv(
    "GSHEETS_SERVICE_ACCOUNT_FILE",
    str(BASE_DIR / "core/keys/crm-sheets.json"),
)
GSHEETS_INQUIRY_TAB = os.getenv("GSHEETS_INQUIRY_TAB", "استفسار عقار")
GSHEETS_PROPERTIES_TAB = os.getenv("GSHEETS_PROPERTIES_TAB", "العقارات المعروضة ")

# =====================================================
# X (TWITTER) API
# =====================================================

X_API_KEY = os.getenv("X_API_KEY")
X_API_KEY_SECRET = os.getenv("X_API_KEY_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET")

# =====================================================
# CORS
# =====================================================

if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
else:
    CORS_ALLOWED_ORIGINS = [
        "https://jodah.onrender.com",
        "https://jodah.sa",
        "https://www.jodah.sa",
    ]

# =====================================================
# PRODUCTION SECURITY (Render)
# =====================================================

CSRF_TRUSTED_ORIGINS = [
    "https://jodah.onrender.com",
    "https://jodah.sa",
    "https://www.jodah.sa",
]
# مطلوب لـ fetch/POST من المتصفح أثناء التطوير على المنفذ المحلي
if DEBUG:
    CSRF_TRUSTED_ORIGINS = list(CSRF_TRUSTED_ORIGINS) + [
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# =====================================================
# بورصة وزارة العدل (SREM) — prod-srem-api-srem.moj.gov.sa
# رمز مدينة جدة مستخدم في GetAreaInfo / GetTrendingDistricts (يمكن تغييره عبر المتغير البيئي).
# =====================================================
SREM_JEDDAH_CITY_SERIAL = int(os.getenv("SREM_JEDDAH_CITY_SERIAL", "37528"))
SREM_DEFAULT_CITY_NAME = os.getenv("SREM_DEFAULT_CITY_NAME", "جدة")
# أولوية GetTrendingDistricts (أحياء بأسماء) على GetAreaInfo — يُنصح بتركه مفعّلاً لجدة
SREM_USE_TRENDING_DISTRICTS = os.getenv("SREM_USE_TRENDING_DISTRICTS", "True").lower() == "true"
# False = إخفاء/تعطيل مزامنة ولوحة بورصة العدل (عند فشل الخدمة أو عدم الحاجة)
SREM_ENABLED = os.getenv("SREM_ENABLED", "True").lower() == "true"
# مدن لوحة «مؤشرات البورصة» في الأدمن (مفصولة بفاصلة، بالعربية كما في قاعدة البيانات)
SREM_DASHBOARD_CITIES = [
    c.strip()
    for c in os.getenv("SREM_DASHBOARD_CITIES", "جدة").split(",")
    if c.strip()
]

# لقطة داخل اليوم (بالساعات) لمسار GetTrendingDistricts.
# أمثلة: 12 => لقطتان يومياً (00:00 و 12:00)، 8 => ثلاث لقطات (00/08/16).
SREM_SNAPSHOT_HOURS = int(os.getenv("SREM_SNAPSHOT_HOURS", "12"))

# مهلات اتصال SREM API (ثواني)
SREM_HTTP_CONNECT_TIMEOUT = float(os.getenv("SREM_HTTP_CONNECT_TIMEOUT", "1.5"))
SREM_HTTP_READ_TIMEOUT = float(os.getenv("SREM_HTTP_READ_TIMEOUT", "3.0"))
SREM_HTTP_RETRIES = int(os.getenv("SREM_HTTP_RETRIES", "0"))
SREM_HTTP_BACKOFF = float(os.getenv("SREM_HTTP_BACKOFF", "0.2"))

# =====================================================
# PROPERTY MATCHING ENGINE (Smart Matching)
# =====================================================
PROPERTY_MATCHING = {
    # أوزان موزّعة (مجموع 1.0): النتيجة = Σ w_i × c_i، كل c_i ∈ [0,1] (انظر listings/services/matching.py)
    "NORM_WEIGHTS": {
        "W_TYPE": 0.33,
        "W_DISTRICT": 0.28,
        "W_BUDGET": 0.27,
        "W_BEHAVIOR": 0.06,
        "W_AREA": 0.02,
        "W_ROOMS": 0.02,
        "W_AGE": 0.02,
    },
    # احتياطي للكود القديم الذي يقرأ أسماء WEIGHT_* فقط — يُشتق منها NORM_WEIGHTS إن لم تُضبط أعلاه
    "WEIGHT_TYPE": 0.40,
    "WEIGHT_DISTRICT": 0.30,
    "WEIGHT_BUDGET": 0.30,
    "WEIGHT_AREA": 0.05,
    "WEIGHT_ROOMS": 0.05,
    "WEIGHT_BEHAVIOR": 0.15,
    "WEIGHT_PROPERTY_AGE": 0.03,
    "THRESHOLD_CANDIDATE": 0.6,
    "THRESHOLD_HIGH_MATCH": 0.8,
    "BUDGET_EXACT_RATIO": 0.20,
    "BUDGET_LOOSE_RATIO": 0.30,
    "MAX_CANDIDATES": 500,
    # أعلى عدد مطابقات تُخزَّن لكل طلب (بعد الفرز تنازلياً حسب النقاط)
    "MAX_MATCHES_TO_PERSIST": 10,
    "REVERSE_MATCH_MAX_REQUESTS": 1000,
    "DISTRICT_GROUPS": None,
}

# =====================================================
# DEFAULT FIELD
# =====================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# =====================================================
# CELERY (Redis broker/backend)
# =====================================================
# Render-friendly: use REDIS_URL as primary source.
# You can override with CELERY_BROKER_URL / CELERY_RESULT_BACKEND explicitly if needed.
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = int(os.environ.get("CELERY_TASK_TIME_LIMIT", "1800"))
CELERY_TASK_SOFT_TIME_LIMIT = int(os.environ.get("CELERY_TASK_SOFT_TIME_LIMIT", "1500"))
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# =====================================================
# DJANGO REST FRAMEWORK
# =====================================================
REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_RATES": {
        # POST /api/property-requests/ — override via env PROPERTY_REQUEST_THROTTLE
        "property_request": os.getenv("PROPERTY_REQUEST_THROTTLE", "60/hour"),
    },
}

# Optional: if set, clients must send header: X-API-Key: <value>
PROPERTY_REQUEST_API_KEY = os.getenv("PROPERTY_REQUEST_API_KEY", "")

# Lead scoring: prime districts (iterable of Arabic names) or comma-separated env LEAD_SCORING_PRIME_DISTRICTS
LEAD_SCORING_PRIME_DISTRICTS = None

# Optional overrides for weights / thresholds (see listings.services.property_request_lead)
LEAD_SCORING_WEIGHTS = {
    "BUDGET_CAP": 35,
    "BUDGET_REF_SAR": 2_000_000,
    "PRIME_DISTRICT": 25,
    "ROOMS": 10,
    "FURNISHED": 5,
    "CATEGORY": 5,
    "NOTES": 10,
    "CONVERSATION_ID": 5,
    "NAME": 5,
    "PRIORITY_HIGH_MIN": 65,
    "PRIORITY_MEDIUM_MIN": 35,
}

# =====================================================
# COMPANY INFORMATION (WHITE-LABEL SETTINGS)
# =====================================================
COMPANY_NAME = os.getenv("COMPANY_NAME", "الركن الأوسط")
COMPANY_NAME_FULL = os.getenv("COMPANY_NAME_FULL", "الركن الأوسط للعقارات")
COMPANY_PHONE = os.getenv("COMPANY_PHONE", "966530460992")
COMPANY_WHATSAPP = os.getenv("COMPANY_WHATSAPP", "966530460992")
COMPANY_INSTAGRAM = os.getenv("COMPANY_INSTAGRAM", "")
COMPANY_X_ACCOUNT = os.getenv("COMPANY_X_ACCOUNT", "")
COMPANY_LINKEDIN = os.getenv("COMPANY_LINKEDIN", "")
COMPANY_SNAPCHAT = os.getenv("COMPANY_SNAPCHAT", "")

# Publishing system default tenant used by admin quick actions.
PUBLISHING_DEFAULT_TENANT_ID = os.getenv("PUBLISHING_DEFAULT_TENANT_ID", "etmam-digital")

# حساب المدير (superuser / لوحة الإدارة): يظهر أولاً في القوائم ويُستخدم في الإسناد الاحتياطي (إشعارات المطابقة، إلخ)
PRIMARY_ADMIN_USERNAME = os.getenv("PRIMARY_ADMIN_USERNAME", "badr9090")

# المسوّق المرجعي «الأول» في القوائم (مثال: أول مسوّق في الفريق — ليس بالضرورة ترتيب الإنشاء في قاعدة البيانات)
PRIMARY_MARKETER_USERNAME = os.getenv("PRIMARY_MARKETER_USERNAME", "b1")

# أسماء مجموعات «المدير المشارك» (مفصولة بفاصلة) لاستخدام القائمة الجانبية الموسّعة
CO_ADMIN_GROUP_NAMES = os.getenv(
    "CO_ADMIN_GROUP_NAMES",
    "مجموعة المدراء المشاركين,المدراء المشاركين,co_admin,co-admin",
)

# =====================================================
# JAZZMIN ADMIN UI CONFIGURATION
# =====================================================
JAZZMIN_SETTINGS = {
    "site_title": f"إدارة {COMPANY_NAME}",
    "site_header": COMPANY_NAME_FULL,
    "site_brand": COMPANY_NAME,
    "site_logo": "img/logo.png",
    "welcome_sign": f"مرحباً بك في لوحة تحكم {COMPANY_NAME}",
    "copyright": COMPANY_NAME_FULL,
    "search_model": [],
    "user_avatar": None,
    "topmenu_links": [
        # بدون قيود صلاحية حتى يرى المسوّقون الروابط (كان auth.view_user يخفي القائمة عنهم)
        {"name": "الرئيسية", "url": "admin:index", "permissions": []},
        {"name": "عرض الموقع", "url": "/", "new_window": True, "permissions": []},
    ],
    # ضمن قسم «إدارة العقارات والطلبات» مثل باقي النماذج (ليس قسمًا منفصلًا)
    "custom_links": {
        "listings": [
            {
                "name": "لوحة الإحصائيات",
                "url": "/marketer/dashboard/",
                "icon": "fas fa-chart-pie",
                "permissions": [],
            },
            {
                "name": "شريط التنبيه",
                "url": "/admin/listings/siteticker/1/change/",
                "icon": "fas fa-bullhorn",
                "permissions": [],
            },
            {
                "name": "البنر الإعلاني",
                "url": "/admin/listings/siteadbanner/1/change/",
                "icon": "fas fa-image",
                "permissions": [],
            },
        ],
    },
    "show_sidebar": True,
    "navigation_expanded": True,
    "hide_apps": [],
    # يظهر كرابط مخصّص «الإشعارات» ضمن listings لتفادي التكرار في القائمة
    "hide_models": ["listings.crmnotification"],
    # توحيد ترتيب القائمة (لنفس الواجهة بين المدير الفائق والمدير المشارك)
    "order_with_respect_to": [
        "auth",
        "auth.user",
        "auth.group",
        "listings",
        "listings.property",
        "listings.propertylead",
        "listings.propertyrequest",
        "listings.propertyoffer",
        "listings.propertymatch",
        "listings.appointment",
        "listings.propertybooking",
        "listings.smartlinkviewlog",
        "listings.propertysmartlink",
        "listings.fastrequest",
        "listings.crmnotification",
        "listings.siteticker",
        "listings.siteadbanner",
        "market",
        "market.realestateindex",
        "market.marketdailyreport",
    ],
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
        "listings": "fas fa-building",
        "listings.Property": "fas fa-building",
        "listings.PropertyOffer": "fas fa-bullhorn",
        "listings.PropertyRequest": "fas fa-search-location",
        "listings.PropertyMatch": "fas fa-link",
        "listings.FastRequest": "fas fa-bolt",
        "listings.PropertySmartLink": "fas fa-external-link-alt",
        "listings.PropertyBooking": "fas fa-calendar-check",
        "listings.Appointment": "fas fa-calendar-day",
        "listings.CRMNotification": "fas fa-bell",
        "listings.SiteTicker": "fas fa-bullhorn",
        "listings.SiteAdBanner": "fas fa-image",
        "listings.GeneralContact": "fas fa-headset",
        "market": "fas fa-chart-line",
        "market.RealEstateIndex": "fas fa-chart-area",
        "market.MarketDailyReport": "fas fa-newspaper",
    },
    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",
    "related_modal_active": False,
    "custom_css": "css/admin_custom.css?v=35",
    "custom_js": "js/admin_custom.js?v=35",
    "use_google_fonts_cdn": True,
    "show_ui_builder": False,
}

JAZZMIN_UI_TWEAKS = {
    "theme": "default",
    "default_theme_mode": "dark",
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": False,
    "accent": "accent-primary",
    "navbar": "navbar-dark",
    "no_navbar_border": False,
    "navbar_fixed": False,
    "layout_boxed": True,
    "footer_fixed": False,
    "sidebar_fixed": False,
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
}

# =====================================================
# LOGGING (Render / Production)
# =====================================================
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        }
    },
    "loggers": {
        # Django internal errors (500 tracebacks)
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        # Our apps
        "market": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "listings": {"handlers": ["console"], "level": "INFO", "propagate": False},
        # Root fallback
        "": {"handlers": ["console"], "level": "WARNING"},
    },
}