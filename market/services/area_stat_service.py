from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, time as dt_time
from typing import Any, Dict, Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_naive, make_aware

from market.models import AreaStat
from market.services.district_service import DistrictService
from market.services.real_estate_api import RealEstateAPIService

logger = logging.getLogger(__name__)

ALL_REGIONS_LABEL = "جميع المناطق"


def _safe_float(val) -> float:
    try:
        if val is None:
            return 0.0
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _parse_trending_district_row(d: Dict[str, Any], default_city: str) -> Optional[Dict[str, Any]]:
    """يستخرج حقول صف الترند مع دعم اختلاف تسمية الحقول."""
    if not isinstance(d, dict):
        return None
    name = (
        (d.get("DistrictName") or d.get("districtName") or d.get("Name") or "")
        .strip()
    )
    tp = _safe_float(d.get("TotalPrice") or d.get("totalPrice"))
    ta = _safe_float(d.get("TotalArea") or d.get("totalArea"))
    tc = int(_safe_float(d.get("TotalCount") or d.get("totalCount")))
    city = (d.get("CityName") or d.get("cityName") or "").strip() or default_city
    if not name or tp <= 0 or ta <= 0:
        return None
    return {
        "name": name,
        "total_price": tp,
        "total_area": ta,
        "total_deals": tc,
        "city_name": city,
    }


class AreaStatService:

    @staticmethod
    def _parse_aggregation_dt(raw_date):
        aggregation_date = parse_datetime(raw_date) if raw_date else None
        if not aggregation_date:
            return None
        if is_naive(aggregation_date):
            aggregation_date = make_aware(aggregation_date)
        return aggregation_date

    @staticmethod
    def _day_anchor_local(day):
        """لقطة يوم واحد (منتصف الليل بتوقيت المشروع) لتخزين صف يومي موحّد."""
        tz = timezone.get_current_timezone()
        return timezone.make_aware(datetime.combine(day, dt_time.min), tz)

    @staticmethod
    def _bucket_anchor_local(now_dt, bucket_hours: int):
        """
        إرجاع بداية بلوك زمني داخل اليوم حسب bucket_hours (8/12...).
        مثال 12: 00:00 أو 12:00، مثال 8: 00/08/16.
        """
        if not bucket_hours or bucket_hours <= 0 or bucket_hours > 24:
            bucket_hours = 12
        tz = timezone.get_current_timezone()
        local_now = timezone.localtime(now_dt, tz)
        h0 = (local_now.hour // bucket_hours) * bucket_hours
        anchored = local_now.replace(hour=h0, minute=0, second=0, microsecond=0)
        return anchored

    @staticmethod
    def _save_one_area_stat(
        *,
        area_name: str,
        aggregation_date,
        city_name,
        total_price: float,
        total_area: float,
        total_deals: int,
        min_price: float,
        max_price: float,
        avg_price: float,
    ):
        price_per_m2 = (total_price / total_area) if total_area > 0 else None
        AreaStat.objects.update_or_create(
            area_name=area_name,
            aggregation_date=aggregation_date,
            period="day",
            defaults={
                "city_name": city_name,
                "avg_price": float(avg_price or 0),
                "min_price": float(min_price or 0),
                "max_price": float(max_price or 0),
                "total_deals": int(total_deals or 0),
                "total_value": float(total_price or 0),
                "total_area": float(total_area or 0),
                "price_per_m2": price_per_m2,
            },
        )

    @staticmethod
    def sync_area_stats():
        """
        جلب بيانات البورصة العقارية (وزارة العدل) وحفظها في AreaStat.
        يُستدعى من المهمة الموحّدة قبل بناء RealEstateIndex.

        الأولوية (جدة/المدينة المعرّفة في SREM_JEDDAH_CITY_SERIAL):
          GetTrendingDistricts — أحياء بأسماء حقيقية ومؤشر ترند رسمي (أفضل من GetAreaInfo
          الذي غالباً يعيد فقط «جميع المناطق» بشرائح ساعية تُضلّل الإجماليات).

        الاحتياط: GetAreaInfo (أحياء مسمّاة، أو تجميع «جميع المناطق» يومياً إن لم يوجد غيره).
        """
        default_city = (getattr(settings, "SREM_DEFAULT_CITY_NAME", "جدة") or "جدة").strip()
        city_code = int(getattr(settings, "SREM_JEDDAH_CITY_SERIAL", 37528))
        use_trending = getattr(settings, "SREM_USE_TRENDING_DISTRICTS", True)

        if use_trending:
            districts = DistrictService.fetch_trending_districts(city_code)
            valid_rows = []
            for d in districts:
                row = _parse_trending_district_row(d, default_city)
                if row:
                    valid_rows.append(row)
            if valid_rows:
                # لقطة داخل اليوم: تجميع حسب بلوك زمني (8/12 ساعة ...)
                bucket = int(getattr(settings, "SREM_SNAPSHOT_HOURS", 12) or 12)
                agg_dt = AreaStatService._bucket_anchor_local(timezone.now(), bucket)
                saved_count = 0
                with transaction.atomic():
                    # لا نحذف تاريخ الأيام السابقة: نحتاج تاريخاً لعرض اتجاهات حقيقية عبر الأيام.
                    # فقط نكتب لقطة اليوم (update_or_create سيحدّث نفس اليوم عند إعادة المزامنة).
                    for row in valid_rows:
                        try:
                            ppm = row["total_price"] / row["total_area"]
                            AreaStat.objects.update_or_create(
                                area_name=row["name"],
                                aggregation_date=agg_dt,
                                period="day",
                                defaults={
                                    "city_name": row["city_name"],
                                    "avg_price": ppm,
                                    "min_price": 0.0,
                                    "max_price": 0.0,
                                    "total_deals": row["total_deals"],
                                    "total_value": row["total_price"],
                                    "total_area": row["total_area"],
                                    "price_per_m2": ppm,
                                },
                            )
                            saved_count += 1
                        except Exception as e:
                            logger.exception("AreaStat TrendingDistricts: %s", e)
                logger.info(
                    "AreaStat: مسار GetTrendingDistricts — %s حي (مدينة %s)",
                    saved_count,
                    default_city,
                )
                if saved_count > 0:
                    return saved_count
            if districts and not valid_rows:
                logger.warning(
                    "GetTrendingDistricts أعاد %s عنصراً لكن لا صفاً صالحاً — الانتقال لـ GetAreaInfo",
                    len(districts),
                )
            elif not districts:
                logger.warning("GetTrendingDistricts فارغ — الانتقال لـ GetAreaInfo")

        data = RealEstateAPIService.fetch_area_stats()

        if not data:
            logger.warning("AreaStat sync: لا توجد بيانات من API")
            return 0

        named = []
        all_regions = []
        for item in data:
            area_name = (item.get("AreaName") or "").strip()
            if not area_name:
                continue
            if area_name == ALL_REGIONS_LABEL:
                all_regions.append(item)
            else:
                named.append(item)

        saved_count = 0
        skipped_count = 0

        with transaction.atomic():
            if named:
                # صفوف لأحياء محددة: لا نكرّر «جميع المناطق» معها
                for item in named:
                    try:
                        area_name = (item.get("AreaName") or "").strip()
                        total_price = float(item.get("TotalPrice") or 0)
                        total_area = float(item.get("TotalArea") or 0)

                        if total_price <= 0 or total_area <= 0:
                            skipped_count += 1
                            continue

                        raw_date = item.get("AggregationDate")
                        aggregation_date = AreaStatService._parse_aggregation_dt(raw_date)
                        if not aggregation_date:
                            logger.warning(
                                "AreaStat: تاريخ غير صالح للحي %s: %s", area_name, raw_date
                            )
                            skipped_count += 1
                            continue

                        city_name = (item.get("CityName") or "").strip() or None
                        price_per_m2 = total_price / total_area

                        AreaStat.objects.update_or_create(
                            area_name=area_name,
                            aggregation_date=aggregation_date,
                            period="day",
                            defaults={
                                "city_name": city_name,
                                "avg_price": float(item.get("AveragePrice") or 0),
                                "min_price": float(item.get("MinPrice") or 0),
                                "max_price": float(item.get("MaxPrice") or 0),
                                "total_deals": int(item.get("TotalCount") or 0),
                                "total_value": total_price,
                                "total_area": total_area,
                                "price_per_m2": price_per_m2,
                            },
                        )
                        saved_count += 1
                    except Exception as e:
                        logger.exception("AreaStat: خطأ في عنصر: %s", e)
                        skipped_count += 1
            elif all_regions:
                # كل الصفوف «جميع المناطق»: تجميع يومي (شرائح ساعية → لقطة يوم واحدة)
                by_day = defaultdict(
                    lambda: {
                        "total_price": 0.0,
                        "total_area": 0.0,
                        "total_deals": 0,
                        "mins": [],
                        "maxs": [],
                        "avg_num": 0.0,
                        "avg_den": 0.0,
                    }
                )
                for item in all_regions:
                    raw_date = item.get("AggregationDate")
                    ad = AreaStatService._parse_aggregation_dt(raw_date)
                    if not ad:
                        skipped_count += 1
                        continue
                    day = timezone.localdate(ad)
                    b = by_day[day]
                    ta = float(item.get("TotalArea") or 0)
                    tp = float(item.get("TotalPrice") or 0)
                    tc = int(item.get("TotalCount") or 0)
                    if ta <= 0 or tp <= 0:
                        skipped_count += 1
                        continue
                    b["total_area"] += ta
                    b["total_price"] += tp
                    b["total_deals"] += tc
                    b["mins"].append(float(item.get("MinPrice") or 0))
                    b["maxs"].append(float(item.get("MaxPrice") or 0))
                    ap = float(item.get("AveragePrice") or 0)
                    if ap > 0:
                        b["avg_num"] += ap * ta
                        b["avg_den"] += ta

                for day, sums in by_day.items():
                    if sums["total_area"] <= 0 or sums["total_price"] <= 0:
                        continue
                    agg_dt = AreaStatService._day_anchor_local(day)
                    min_p = min(sums["mins"]) if sums["mins"] else 0.0
                    max_p = max(sums["maxs"]) if sums["maxs"] else 0.0
                    if sums["avg_den"] > 0:
                        avg_p = sums["avg_num"] / sums["avg_den"]
                    else:
                        avg_p = sums["total_price"] / sums["total_area"]

                    AreaStatService._save_one_area_stat(
                        area_name=ALL_REGIONS_LABEL,
                        aggregation_date=agg_dt,
                        city_name=default_city,
                        total_price=sums["total_price"],
                        total_area=sums["total_area"],
                        total_deals=sums["total_deals"],
                        min_price=min_p,
                        max_price=max_p,
                        avg_price=avg_p,
                    )
                    saved_count += 1

                logger.info(
                    "AreaStat: مسار تجميع «جميع المناطق» يومياً — أيام=%s صفوف=%s",
                    len(by_day),
                    saved_count,
                )
            else:
                logger.warning("AreaStat sync: لا توجد صفوف صالحة بعد التصفية")

        logger.info("AreaStat sync: محفوظ=%s متخطى=%s", saved_count, skipped_count)
        return saved_count