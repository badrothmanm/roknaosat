"""
مسار موحّد لبورصة وزارة العدل (SREM):
  API → جدول AreaStat → جدول RealEstateIndex (صف واحد لكل حي: property_type = «all»)

لا يُولَّد سعر متر من عشوائية: القيم مطابقة لما يُخزَّن من AreaStat بعد المزامنة.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List

from django.conf import settings
from django.db.models import Max

from market.models import AreaStat, MarketDailyReport, RealEstateIndex

logger = logging.getLogger(__name__)

AGGREGATE_NEIGHBORHOOD_LABEL = "جميع المناطق"


def sync_realestate_index_from_area_stats() -> int:
    """
    يبني/يحدّث RealEstateIndex من آخر يوم تقويمي له بيانات في AreaStat.
    يجمع صفوف نفس (المدينة، الحي) في ذلك اليوم — لتفادي تكرار شرائح ساعية أو مزامنات جزئية.
    يحذف صفوف الأنواع القديمة (أرض/شقة/فيلا) لنفس الحي والتاريخ.
    """
    # نبني RealEstateIndex من أحدث لقطة (aggregation_date) — يدعم لقطات متعددة داخل اليوم.
    base = AreaStat.objects.exclude(aggregation_date__isnull=True).filter(period="day")
    if not base.exists():
        logger.warning("srem_pipeline: لا توجد سجلات AreaStat — لن يُحدَّث RealEstateIndex")
        return 0

    fetch_dt = base.aggregate(m=Max("aggregation_date")).get("m")
    if not fetch_dt:
        logger.warning("srem_pipeline: تعذر تحديد تاريخ اللقطة من AreaStat")
        return 0

    day_rows = AreaStat.objects.exclude(aggregation_date__isnull=True).filter(
        period="day",
        aggregation_date=fetch_dt,
    )
    if not day_rows.exists():
        logger.warning(
            "srem_pipeline: لا صفوف AreaStat للّقطة %s — تحقق من المزامنة",
            fetch_dt,
        )
        return 0

    fetch_date = fetch_dt.date()

    rows_out: List[Dict[str, Any]] = []
    count = 0

    default_city = getattr(settings, "SREM_DEFAULT_CITY_NAME", "جدة")

    # لم نعد نستخدم صف «جميع المناطق» بعد التحويل إلى TrendingDistricts
    RealEstateIndex.objects.filter(
        date=fetch_date,
        period="day",
        neighborhood=AGGREGATE_NEIGHBORHOOD_LABEL,
    ).delete()

    grouped: Dict[tuple, Dict[str, float]] = defaultdict(
        lambda: {
            "total_area": 0.0,
            "total_value": 0.0,
            "total_deals": 0,
            "ppm_weighted_num": 0.0,
            "ppm_weighted_den": 0.0,
        }
    )

    for stat in day_rows:
        city = (stat.city_name or "").strip() or default_city
        key = (city, stat.area_name)
        g = grouped[key]
        ta = float(stat.total_area or 0)
        tv = float(stat.total_value or 0)
        g["total_area"] += ta
        g["total_value"] += tv
        g["total_deals"] += int(stat.total_deals or 0)
        ppm = float(stat.price_per_m2 or 0)
        if ppm > 0 and ta > 0:
            g["ppm_weighted_num"] += ppm * ta
            g["ppm_weighted_den"] += ta

    for (city, area_name), g in grouped.items():
        RealEstateIndex.objects.filter(
            city=city,
            neighborhood=area_name,
            date=fetch_date,
            period="day",
        ).exclude(property_type="all").delete()

        t_area = g["total_area"]
        t_val = g["total_value"]
        if g["ppm_weighted_den"] > 0:
            price = g["ppm_weighted_num"] / g["ppm_weighted_den"]
        elif t_area > 0 and t_val > 0:
            price = t_val / t_area
        else:
            price = 0.0
        price = round(float(price), 2)

        RealEstateIndex.objects.update_or_create(
            city=city,
            neighborhood=area_name,
            property_type="all",
            date=fetch_date,
            period="day",
            defaults={
                "num_deals": int(g["total_deals"]),
                "total_value_sar": t_val,
                "traded_area_sqm": t_area,
                "avg_price_per_m2": price,
            },
        )
        count += 1
        rows_out.append(
            {
                "city": city,
                "neighborhood": area_name,
                "property_type": "all",
                "source": "moj_srem_api",
                "num_deals": int(g["total_deals"]),
                "traded_area_sqm": t_area,
                "total_value_sar": t_val,
                "avg_price_per_m2": price,
            }
        )

    MarketDailyReport.objects.update_or_create(
        date=fetch_date,
        defaults={
            "succeeded": True,
            "raw_snapshot": rows_out,
        },
    )
    logger.info("srem_pipeline: تم تحديث %s صفاً في RealEstateIndex من AreaStat", count)
    return count
