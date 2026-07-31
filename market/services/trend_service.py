"""
حساب اتجاهات الأسعار بين لقطتين زمنيتين مختلفتين.
المشكلة السابقة: مقارنة آخر سجلين بـ created_at فقط غالباً تعطي نفس السعر (0%).
مقارنة RealEstateIndex تُصفّى حسب المدينة (SREM_DASHBOARD_CITIES) لتفادي خلط أحياء بنفس الاسم بين مدن.
"""
import logging
from collections import defaultdict

from django.conf import settings
from django.utils import timezone

from market.models import AreaStat, RealEstateIndex

logger = logging.getLogger(__name__)

# صف المجموع من GetAreaInfo — لا يُستخدم في مقارنات الترند (مضلّل أو مكرر)
AGGREGATE_AREA_LABEL = "جميع المناطق"


class TrendService:

    @staticmethod
    def _snapshot_key(record: AreaStat):
        """
        مفتاح اللقطة: aggregation_date إن وُجد (يدعم عدة لقطات في اليوم)،
        وإلا created_at.
        """
        if record.aggregation_date:
            return record.aggregation_date
        return record.created_at

    @staticmethod
    def _trends_from_area_stat(cities_filter=None):
        """
        لكل حي: آخر صف لكل لقطة (aggregation_date)، ثم مقارنة آخر لقطتين مختلفتين.
        يُفضّل تمرير cities_filter حتى يطابق المدن التي تعرضها صفحة الأدمن.
        """
        if cities_filter is None:
            cities_filter = [
                c.strip()
                for c in getattr(settings, "SREM_DASHBOARD_CITIES", []) or []
                if c and str(c).strip()
            ]
        cities = cities_filter or []
        base = AreaStat.objects.all()
        if cities:
            base = base.filter(city_name__in=cities)
        areas = base.values_list("area_name", flat=True).distinct()
        results = []

        for area in areas:
            rows = (
                AreaStat.objects.filter(area_name=area)
                .order_by("-aggregation_date", "-created_at")
            )
            if cities:
                rows = rows.filter(city_name__in=cities)
            # أحدث صف لكل لقطة (aggregation_date)
            by_snap = {}
            for r in rows:
                k = TrendService._snapshot_key(r)
                if k is None:
                    continue
                if k not in by_snap:
                    by_snap[k] = r

            sorted_snaps = sorted(by_snap.keys(), reverse=True)
            if len(sorted_snaps) < 2:
                continue

            new = by_snap[sorted_snaps[0]].price_per_m2
            old = by_snap[sorted_snaps[1]].price_per_m2

            if new is None or old is None or old == 0:
                continue

            trend = ((new - old) / old) * 100
            results.append({"area": area, "trend": round(trend, 2)})

        return results

    @staticmethod
    def _weighted_avg_price_m2(neighborhood: str, on_date, period: str = "day", city: str | None = None):
        """
        متوسط مرجّح لسعر المتر للحي في تاريخ معيّن (صف property_type=all كما في لوحة الوزارة).
        """
        qs = RealEstateIndex.objects.filter(
            neighborhood=neighborhood,
            date=on_date,
            period=period,
            property_type="all",
        )
        if city:
            qs = qs.filter(city=city)
        rows = list(qs)
        if not rows:
            return None

        total_area = sum((r.traded_area_sqm or 0) for r in rows)
        if total_area > 0:
            num = sum((r.avg_price_per_m2 or 0) * (r.traded_area_sqm or 0) for r in rows)
            return num / total_area

        vals = [r.avg_price_per_m2 for r in rows if r.avg_price_per_m2]
        if not vals:
            return None
        return sum(vals) / len(vals)

    @staticmethod
    def _trends_real_estate_for_date_pair(
        new_date,
        old_date,
        *,
        period: str = "day",
        cities_filter=None,
    ):
        """حساب الترند لكل (مدينة، حي) بين تاريخين."""
        if cities_filter is None:
            cities_filter = [
                c.strip()
                for c in getattr(settings, "SREM_DASHBOARD_CITIES", []) or []
                if c and str(c).strip()
            ]

        cities_filter = [c for c in (cities_filter or []) if c and str(c).strip()]
        if not cities_filter:
            cities_filter = list(
                RealEstateIndex.objects.filter(
                    date__in=(new_date, old_date), period=period
                )
                .values_list("city", flat=True)
                .distinct()
            )

        results = []
        multi_city = len(cities_filter) > 1

        for city in cities_filter:
            n_new = set(
                RealEstateIndex.objects.filter(
                    date=new_date, period=period, city=city
                ).values_list("neighborhood", flat=True)
            )
            n_old = set(
                RealEstateIndex.objects.filter(
                    date=old_date, period=period, city=city
                ).values_list("neighborhood", flat=True)
            )
            common = n_new & n_old
            common = {
                n
                for n in common
                if n and n.strip() and n.strip() != AGGREGATE_AREA_LABEL
            }
            for neighborhood in sorted(common):
                p_new = TrendService._weighted_avg_price_m2(
                    neighborhood, new_date, period=period, city=city
                )
                p_old = TrendService._weighted_avg_price_m2(
                    neighborhood, old_date, period=period, city=city
                )
                if p_new is None or p_old is None or p_old == 0:
                    continue
                trend = ((p_new - p_old) / p_old) * 100
                label = neighborhood
                if multi_city:
                    label = f"{neighborhood} ({city})"
                results.append({"area": label, "trend": round(trend, 2)})

        return results

    @staticmethod
    def _trends_from_real_estate_index(cities_filter=None):
        """
        يعتمد على RealEstateIndex لكل (مدينة، حي).

        أولاً: مقارنة آخر يومين تقويميين في الجدول.
        إذا كانت كل النسب ~0% (نفس الأسعار بين يومين متتاليين أو تكرار مزامنة)،
        نجرّب مقارنة **أحدث لقطة** بـ **أقدم لقطة** في قاعدة البيانات لنفس المدن/الأحياء.
        """
        period = "day"
        qs = RealEstateIndex.objects.filter(period=period)
        if cities_filter:
            qs = qs.filter(city__in=cities_filter)
        all_dates = set(qs.values_list("date", flat=True))
        if len(all_dates) < 2:
            return []

        sorted_dates = sorted(all_dates, reverse=True)
        new_date, old_date = sorted_dates[0], sorted_dates[1]

        results = TrendService._trends_real_estate_for_date_pair(
            new_date,
            old_date,
            period=period,
            cities_filter=cities_filter,
        )

        meaningful = [r for r in results if abs(r["trend"]) >= 0.05]
        if len(sorted_dates) > 2 and len(meaningful) == 0 and results:
            oldest = sorted_dates[-1]
            if oldest != old_date:
                alt = TrendService._trends_real_estate_for_date_pair(
                    new_date,
                    oldest,
                    period=period,
                    cities_filter=cities_filter,
                )
                if alt:
                    logger.info(
                        "TrendService: اليومان الأخيران يعطيان ~0%% — استُخدمت مقارنة "
                        "%s مقابل أقدم لقطة %s.",
                        new_date,
                        oldest,
                    )
                    results = alt

        return results

    @staticmethod
    def _label_for_trend(trend: float) -> str:
        if trend > 5:
            return "🔥 صاعد بقوة"
        if trend > 0:
            return "🟢 صاعد"
        if trend < -5:
            return "⚠️ هبوط قوي"
        if trend < 0:
            return "🔻 هابط"
        return "➖ ثابت"

    @staticmethod
    def calculate_trends(cities=None):
        """
        أولوية: RealEstateIndex (تاريخان مختلفان + أحياء مشتركة).
        احتياط: AreaStat بلقطات أيام مميزة.
        """
        results = TrendService._trends_from_real_estate_index(cities_filter=cities)
        if not results:
            results = TrendService._trends_from_area_stat(cities_filter=cities)
            if not results:
                logger.info(
                    "TrendService: لا توجد اتجاهات — يحتاج RealEstateIndex لتاريخين "
                    "أو AreaStat ليومين مختلفين لكل حي."
                )

        results = sorted(results, key=lambda x: x["trend"], reverse=True)

        for r in results:
            r["label"] = TrendService._label_for_trend(r["trend"])

        eps = 0.005
        top_rising = [r for r in results if r["trend"] > eps][:3]
        top_falling = [r for r in results if r["trend"] < -eps][:3]
        stable = [r for r in results if abs(r["trend"]) <= eps][:3]

        return {
            "all": results,
            "rising": top_rising,
            "falling": top_falling,
            "stable": stable,
        }
