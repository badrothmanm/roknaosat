import logging
import urllib.parse

from django.contrib import admin
from django.conf import settings
from django.urls import path, reverse
from django.utils import timezone
from django.shortcuts import render, redirect
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseRedirect,
)
from django.db import models

from .models import RealEstateIndex, MarketDailyReport
from .tasks import run_fetch_and_store_srem_indices
from market.services.trend_service import TrendService

logger = logging.getLogger(__name__)

# مسار احتياطي إذا فشل reverse (أسماء URL مختلفة بين البيئات)
DASHBOARD_PATH = "/admin/market/realestateindex/dashboard/"


def _safe_admin_msg(text: str, max_len: int = 500) -> str:
    """تقليص نص الرسالة لتجنّب تجاوز حد الجلسة/الكوكي."""
    s = str(text)
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s


def _redirect_dashboard_with_srem_sync(**params) -> HttpResponse:
    """إعادة توجيه للداشبورد مع نتيجة المزامنة في الـ query (بدون django messages / جلسة)."""
    filtered = {k: v for k, v in params.items() if v is not None and v != ""}
    q = urllib.parse.urlencode(filtered, safe="")
    try:
        base = reverse("admin:market_realestateindex_dashboard")
    except Exception:
        base = DASHBOARD_PATH.rstrip("/")
    return HttpResponseRedirect(f"{base}?{q}" if q else base)


def _srem_sync_banner_from_request(request: HttpRequest):
    """
    يقرأ ?srem_sync= من الرابط بعد «تحديث الآن».
    يُفضّل على messages لتجنّب أعطال تخزين الرسائل في الجلسة على بعض الاستضافات.
    """
    sync = request.GET.get("srem_sync")
    if not sync:
        return None
    reason = (request.GET.get("reason") or "").strip()
    if sync == "ok":
        n = request.GET.get("n", "")
        m = request.GET.get("m", "")
        return {
            "level": "success",
            "text": f"تم التحديث: AreaStat={n} صفاً، RealEstateIndex={m} صفاً.",
        }
    if sync == "err":
        return {
            "level": "danger",
            "text": _safe_admin_msg(reason or "تعذر تشغيل التحديث.", 800),
        }
    if sync == "warn":
        return {
            "level": "warning",
            "text": "خدمة بورصة العدل معطّلة (SREM_ENABLED=False).",
        }
    if sync == "none":
        return {
            "level": "danger",
            "text": (
                "لم تُحفظ أي بيانات من بورصة العدل. تحقق من اتصال الخادم بـ "
                "prod-srem-api-srem.moj.gov.sa أو رمز المدينة SREM_JEDDAH_CITY_SERIAL."
            ),
        }
    if sync == "fatal":
        return {
            "level": "danger",
            "text": _safe_admin_msg(reason or "خطأ غير متوقع.", 800),
        }
    return None


@admin.register(RealEstateIndex)
class RealEstateIndexAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "city",
        "neighborhood",
        "traded_area_sqm",
        "total_value_sar",
        "avg_price_per_m2",
        "period",
    )
    list_filter = ("city", "date")
    search_fields = ("neighborhood",)
    date_hierarchy = "date"
    change_list_template = "admin/market/realestateindex/dashboard.html"

    def has_module_permission(self, request: HttpRequest) -> bool:
        return bool(request.user and request.user.is_staff)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "dashboard/",
                self.admin_site.admin_view(self.dashboard_view),
                name="market_realestateindex_dashboard",
            ),
            path(
                "refresh-now/",
                self.admin_site.admin_view(self.refresh_now_view),
                name="market_realestateindex_refresh_now",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        return redirect("admin:market_realestateindex_dashboard")

    def dashboard_view(self, request: HttpRequest) -> HttpResponse:
        if not request.user.is_staff:
            return HttpResponseForbidden("غير مصرح لك بالدخول.")

        srem_sync_banner = _srem_sync_banner_from_request(request)
        selected_section = (request.GET.get("section") or "results").strip().lower()
        if selected_section not in ("results", "trends", "all"):
            selected_section = "results"

        if not getattr(settings, "SREM_ENABLED", True):
            context = {
                **self.admin_site.each_context(request),
                "title": "مؤشرات البورصة العقارية — معطّلة",
                "srem_disabled": True,
                "srem_sync_banner": srem_sync_banner,
                "selected_section": selected_section,
            }
            return render(request, "admin/market/realestateindex/dashboard.html", context)

        # المزامنة تُخزّن فقط period=day — أي اختيار آخر كان يُرجع صفر صفوف دائماً
        selected_period = "day"

        # أحياء/مدن لوحة «مؤشرات البورصة» (نستخدم نفس المدن في اختيار تاريخ اللقطة)
        dashboard_cities = [
            c.strip()
            for c in getattr(settings, "SREM_DASHBOARD_CITIES", ["جدة"])
            if c.strip()
        ]

        latest_entry = RealEstateIndex.objects.filter(
            period=selected_period,
            city__in=dashboard_cities,
        ).order_by("-date").first()
        if latest_entry:
            view_date = latest_entry.date
        else:
            view_date = timezone.localtime().date()

        # صفوف «الكل» من مسار بورصة الوزار لنفس تاريخ اللقطة
        indices_base = RealEstateIndex.objects.filter(
            date=view_date,
            period=selected_period,
            property_type="all",
        ).order_by("city", "neighborhood")
        indices = indices_base.filter(city__in=dashboard_cities)
        city_filter_mismatch = False
        if not indices.exists() and indices_base.exists():
            # بيانات موجودة لكن اسم المدينة لا يطابق القائمة (فراغات، أو إعداد خاطئ)
            indices = indices_base
            city_filter_mismatch = True

        cities_for_cards = (
            list(indices.values_list("city", flat=True).distinct())
            if city_filter_mismatch
            else dashboard_cities
        )

        city_cards = []
        for city in cities_for_cards:
            qs = indices.filter(city=city)
            total_area = qs.aggregate(total=models.Sum("traded_area_sqm"))["total"] or 0
            total_value = qs.aggregate(total=models.Sum("total_value_sar"))["total"] or 0
            total_deals = qs.aggregate(total=models.Sum("num_deals"))["total"] or 0
            # متوسط المدينة = إجمالي القيمة / إجمالي المساحة (أدق من متوسط المعدلات)
            avg_price = (float(total_value) / float(total_area)) if total_area else 0
            city_cards.append(
                {
                    "city": city,
                    "total_traded_area_sqm": total_area,
                    "total_value": total_value,
                    "total_deals": total_deals,
                    "avg_price": avg_price,
                    "rows_count": qs.count(),
                }
            )

        # وصف مصدر لقطات الجدول التفصيلي (كما في لوحة المسوّق)
        indices_data_note = ""
        snap = MarketDailyReport.objects.filter(date=view_date).order_by("-generated_at").first()
        if snap and snap.raw_snapshot:
            raw = snap.raw_snapshot
            rows = raw if isinstance(raw, list) else []
            moj = sum(
                1
                for r in rows
                if isinstance(r, dict)
                and r.get("source") in ("moj_srem_api", "moj_anchor")
            )
            if moj:
                indices_data_note = (
                    "البيانات من مؤشر الترند ببورصة وزارة العدل: لكل حي معروض — إجمالي الصفقات والمساحة والقيمة، "
                    "ومتوسط سعر المتر = القيمة ÷ المساحة (صف «الكل»)."
                )
            else:
                indices_data_note = (
                    "لم تُعلَّم اللقطة بمصدر API — اضغط «تحديث الآن» أعلاه بعد المزامنة."
                )
        if not indices_data_note:
            indices_data_note = (
                "لا توجد لقطة يومية موثّقة — استخدم «تحديث الآن» لجلب بيانات البورصة."
            )

        # Get Market Trends (احسب الترند لنفس المدن الظاهرة في الصفحة)
        try:
            trends = TrendService.calculate_trends(cities=cities_for_cards)
            all_trends_list = trends["all"]
        except Exception as e:
            logger.exception("TrendService.calculate_trends failed: %s", e)
            all_trends_list = []
        
        # Determine market status
        is_rising = any(t["trend"] > 0 for t in all_trends_list)
        is_falling = any(t["trend"] < 0 for t in all_trends_list)

        # أفضل/أسوأ حي فقط عند وجود حيّين على الأقل (تجنّب تكرار نفس الاسم بنسبتين متضادتين)
        best_trend = worst_trend = None
        if len(all_trends_list) >= 2:
            best_trend = all_trends_list[0]
            worst_trend = all_trends_list[-1]

        context = {
            **self.admin_site.each_context(request),
            "title": "تحليل يومي — البورصة العقارية",
            "srem_disabled": False,
            "srem_sync_banner": srem_sync_banner,
            "selected_section": selected_section,
            "period_mode_note": (
                "المزامنة الحالية يومية فقط (صفوف period=day). تم إيقاف فلترة أسبوع/شهر/سنة في الواجهة "
                "لأنها كانت تُظهر لوحة فارغة رغم نجاح المزامنة."
            ),
            "indices": indices,
            "city_cards": city_cards,
            "dashboard_cities": dashboard_cities,
            "city_filter_mismatch": city_filter_mismatch,
            "dashboard_data_note": (
                "الأرقام من آخر مزامنة ناجحة مع بورصة وزارة العدل: أحياء مؤشر الترند (GetTrendingDistricts) "
                "ثم RealEstateIndex — المدن المعروضة: "
                + "، ".join(dashboard_cities)
                + ". إجمالي البطاقة = مجموع الأحياء المعروضة في الترند وليس بالضرورة كل المدينة. "
                "تاريخ اللقطة: "
                + view_date.strftime("%Y-%m-%d")
                + "."
            ),
            "indices_date": view_date,
            "indices_data_note": indices_data_note,
            "all_trends": all_trends_list,
            "best_trend": best_trend,
            "worst_trend": worst_trend,
            "rising": is_rising,
            "falling": is_falling,
            "today": view_date,
            "selected_period": selected_period,
        }
        return render(request, "admin/market/realestateindex/dashboard.html", context)

    def refresh_now_view(self, request: HttpRequest) -> HttpResponse:
        try:
            if not getattr(request.user, "is_staff", False):
                return HttpResponseForbidden("غير مصرح لك بالدخول.")
        except Exception:
            logger.exception("refresh_now_view: staff check")
            return _redirect_dashboard_with_srem_sync(
                srem_sync="fatal",
                reason="تعذر التحقق من صلاحية المستخدم.",
            )

        try:
            if not getattr(settings, "SREM_ENABLED", True):
                return _redirect_dashboard_with_srem_sync(srem_sync="warn")

            n, m, pipeline_err = run_fetch_and_store_srem_indices()
            if pipeline_err:
                return _redirect_dashboard_with_srem_sync(
                    srem_sync="err",
                    reason=_safe_admin_msg(pipeline_err, 400),
                )
            if n == 0:
                return _redirect_dashboard_with_srem_sync(srem_sync="none")
            return _redirect_dashboard_with_srem_sync(srem_sync="ok", n=n, m=m)
        except Exception as exc:
            logger.exception("refresh_now_view failed: %s", exc)
            return _redirect_dashboard_with_srem_sync(
                srem_sync="fatal",
                reason=_safe_admin_msg(str(exc), 400),
            )


@admin.register(MarketDailyReport)
class MarketDailyReportAdmin(admin.ModelAdmin):
    list_display = ("date", "generated_at", "succeeded")
    list_filter = ("succeeded", "date")
    readonly_fields = ("date", "generated_at", "raw_snapshot", "succeeded", "error_message")

    def has_module_permission(self, request: HttpRequest) -> bool:
        return bool(request.user and request.user.is_staff)
