import logging
from typing import Dict, List, Optional

from django.conf import settings

from market.services.srem_client import SremClient

logger = logging.getLogger(__name__)


class RealEstateAPIService:
    """
    طبقة رقيقة فوق SREM API — جلب إحصائيات المناطق (Stats) لحفظها في AreaStat.
    """

    @staticmethod
    def fetch_area_stats(city_code: Optional[int] = None) -> List[Dict]:
        try:
            code = city_code
            if code is None:
                code = int(getattr(settings, "SREM_JEDDAH_CITY_SERIAL", 37528))

            client = SremClient()
            response = client.get_area_info(city_code=code)

            ok = bool(response.get("IsSuccess") or response.get("isSuccess"))
            if not ok:
                logger.warning("SREM API: success flag false — %s", response.get("Message") or response)
                return []

            data = response.get("Data") or {}
            stats = data.get("Stats") or []

            if not stats:
                logger.warning("SREM API: Stats فارغة — جرّب SREM_JEDDAH_CITY_SERIAL=0 لجميع المدن أو رمز مدينة أخرى")
                return []

            return stats

        except Exception as e:
            logger.exception("SREM fetch_area_stats: %s", e)
            return []