from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r"properties", views.PropertyViewSet)
router.register(r"n8n/properties", views.N8NPropertyViewSet, basename="n8n-properties")

app_name = "listings"

urlpatterns = [
    path("", views.home, name="home"),
    path("itmam-brochure/", views.itmam_brochure, name="itmam-brochure"),
    path("api/", include(router.urls)),
    path("contact/", views.contact, name="contact"),
    path("submit-property/", views.submit_property, name="submit-property"),

    path("api/properties/<int:pk>/inquiry/", views.property_inquiry_api, name="api-property-inquiry"),
    path("api/offer-property/", views.api_offer_property, name="api_offer_property"),
    path("api/general-contact/", views.general_contact_api, name="api-general-contact"),

    # ✅ Property Request API – Production-Ready (DB save + Matching Engine)
    path("api/request-property/", views.property_request_api, name="request_property_api"),
    path("api/property-request/", views.property_request_api, name="property-request-api"),
    path(
        "api/property-requests/",
        views.PropertyRequestCreateAPIView.as_view(),
        name="property-requests-create",
    ),
    path(
        "api/n8n/property-request/",
        views.N8nPropertyRequestCreateAPIView.as_view(),
        name="n8n-property-request-create",
    ),
    # نفس الـ view — للتوافق مع عناوين n8n بدون بادئة api/
    path(
        "n8n/property-request/",
        views.N8nPropertyRequestCreateAPIView.as_view(),
        name="n8n-property-request",
    ),



    # فتح العقار برقم العقار (listing_id) — يجب أن يسبق المسار الرقمي لتفادي التعارض
    path("property/l/<str:listing_id>/", views.property_detail_by_listing_id, name="property-detail-by-listing"),
    path("property/<int:pk>/", views.property_detail, name="property-detail"),
    path("property/<int:pk>/appointment/", views.create_property_appointment, name="appointment-create"),
    path("appointments/cancel/<uuid:token>/", views.cancel_appointment, name="appointment-cancel"),
    path("property/<int:pk>/qr/", views.property_qr_card, name="property_qr"),

    # API لإنشاء الرابط الذكي
    path("api/properties/<int:pk>/smart-link/", views.generate_smart_link, name="api-smart-link"),
    path("marketer/dashboard/", views.marketer_dashboard_view, name="marketer-dashboard"),
    # تبديل المدير إلى حساب مسوّق دون تسجيل خروج
    path("staff/impersonate/start/", views.impersonate_start_view, name="impersonate-start"),
    path("staff/impersonate/stop/", views.impersonate_stop_view, name="impersonate-stop"),
    # عرض البروشور الذكي (المسار الرسمي)
    path("s/<str:token>/", views.smart_brochure_view, name="smart-brochure"),
    # توافق مع روابط قديمة/خاطئة كانت تستخدم /listings/s/<token>/
    path("listings/s/<str:token>/", views.smart_brochure_view, name="smart-brochure-legacy"),
    # لوحة أداء المالك
    path("admin/property/<int:pk>/performance/", views.owner_performance_view, name="owner-performance"),

    # n8n Booking API
    path("api/n8n/book-viewing/", views.create_booking_api, name="api-n8n-book-viewing"),

    path("privacy/", views.privacy, name="privacy"),
    path("terms/", views.terms, name="terms"),
    path("request-property/", views.request_property, name="request-property"),

    # Smart Site Card
    path("link/", views.smart_site_card_view, name="smart-site-card"),
    path("api/fast-request/", views.api_submit_fast_request, name="api-fast-request"),
    path("api/listings/", views.api_listings, name="api-listings"),
    path("api/admin-stats/", views.admin_stats_api, name="api-admin-stats"),
    path("api/admin/marketers/", views.api_get_marketers, name="api-admin-marketers"),
    path("api/marketer/links/activate/", views.api_activate_marketer_link, name="api-activate-marketer-link"),
    path("api/admin/generate-ai-copy/", views.generate_ai_copy, name="api-generate-ai-copy"),
    path("api/bulk/", views.api_bulk_properties, name="api-bulk-properties"),
    path("api/properties/<int:pk>/similar/", views.api_similar_properties, name="api-similar-properties"),
]
