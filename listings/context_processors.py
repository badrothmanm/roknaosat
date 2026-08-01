import os
import json
import datetime
from django.conf import settings
from django.urls import reverse


def global_vars(request):
    impersonator = getattr(request, "impersonator", None)
    try:
        impersonate_start_url = reverse("listings:impersonate-start")
        impersonate_stop_url = reverse("listings:impersonate-stop")
    except Exception:
        impersonate_start_url = ""
        impersonate_stop_url = ""

    site_ticker = None
    site_ad_banner = None
    site_ad_banner_json = "{}"
    try:
        from listings.models import SiteTicker, SiteAdBanner
        site_ticker = SiteTicker.load()
        site_ad_banner = SiteAdBanner.load()
        site_ad_banner_json = json.dumps(
            site_ad_banner.as_frontend_config(),
            ensure_ascii=False,
        )
    except Exception:
        site_ticker = None
        site_ad_banner = None
        site_ad_banner_json = "{}"

    try:
        from listings.riyadh_districts import (
            RIYADH_DISTRICTS,
            BUDGET_RANGES_BUY,
            BUDGET_RANGES_RENT,
            ROOM_OPTIONS,
            BATHROOM_OPTIONS,
        )
    except Exception:
        RIYADH_DISTRICTS = []
        BUDGET_RANGES_BUY = []
        BUDGET_RANGES_RENT = []
        ROOM_OPTIONS = []
        BATHROOM_OPTIONS = []

    return {
        "primary_marketer_username": getattr(settings, "PRIMARY_MARKETER_USERNAME", "b1"),
        "company_name": getattr(settings, "COMPANY_NAME", "جودة المستقبل"),
        "company_name_full": getattr(
            settings, "COMPANY_NAME_FULL", "جودة المستقبل للتطوير والاستثمار العقاري"
        ),
        "company_phone": getattr(settings, "COMPANY_PHONE", ""),
        "company_whatsapp": getattr(settings, "COMPANY_WHATSAPP", ""),
        "company_instagram": getattr(settings, "COMPANY_INSTAGRAM", ""),
        "company_x_account": getattr(settings, "COMPANY_X_ACCOUNT", ""),
        "company_linkedin": getattr(settings, "COMPANY_LINKEDIN", ""),
        "company_snapchat": getattr(settings, "COMPANY_SNAPCHAT", ""),
        "license_number": "1200012345",
        "location": "جدة، المملكة العربية السعودية",
        "current_year": datetime.datetime.now().year,
        "apps_script_url": os.getenv("APPS_SCRIPT_URL"),
        "apps_script_key": os.getenv("APPS_SCRIPT_KEY"),
        "submission_url": os.getenv("SUBMISSION_URL"),
        "crm_url": os.getenv("CRM_URL", os.getenv("APPS_SCRIPT_URL")),
        "crm_key": os.getenv("CRM_KEY", os.getenv("APPS_SCRIPT_KEY")),
        "impersonator": impersonator,
        "is_impersonating": impersonator is not None,
        "impersonate_start_url": impersonate_start_url,
        "impersonate_stop_url": impersonate_stop_url,
        "site_ticker": site_ticker,
        "site_ad_banner": site_ad_banner,
        "site_ad_banner_json": site_ad_banner_json,
        "riyadh_districts": RIYADH_DISTRICTS,
        "budget_ranges_buy": BUDGET_RANGES_BUY,
        "budget_ranges_rent": BUDGET_RANGES_RENT,
        "room_options": ROOM_OPTIONS,
        "bathroom_options": BATHROOM_OPTIONS,
    }
