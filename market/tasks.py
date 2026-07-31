import logging

from django.conf import settings

from market.services.area_stat_service import AreaStatService
from market.services.srem_pipeline import sync_realestate_index_from_area_stats

logger = logging.getLogger(__name__)


def run_fetch_and_store_srem_indices():
    """
    مسار واحد لبورصة وزارة العدل:
      1) جلب وحفظ AreaStat (أولوية: GetTrendingDistricts، احتياط: GetAreaInfo)
      2) بناء RealEstateIndex من تلك اللقطات (صف «الكل» لكل حي)

    لا تُستخدم print() بنص عربي — على Windows قد يسبب UnicodeEncodeError ويُسقط الطلب (500).

    Returns:
        (area_stat_count, reindex_count, error_message)
        error_message: None عند النجاح، أو نص خطأ عند الاستثناء (لا يُرفع استثناء للواجهة).
    """
    if not getattr(settings, "SREM_ENABLED", True):
        logger.info("SREM: service disabled (SREM_ENABLED=False)")
        return (0, 0, None)

    try:
        logger.info("SREM sync started")

        n = AreaStatService.sync_area_stats()
        if n == 0:
            logger.error(
                "SREM: no AreaStat rows saved — check network, SREM_JEDDAH_CITY_SERIAL, or API."
            )
            return (0, 0, None)

        m = sync_realestate_index_from_area_stats()
        logger.info("SREM sync done: AreaStat rows=%s RealEstateIndex rows=%s", n, m)
        return (n, m, None)

    except Exception as e:
        logger.exception("SREM pipeline failed")
        return (0, 0, str(e))


def run_quick_refresh():
    run_fetch_and_store_srem_indices()
