import logging
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from django.conf import settings

logger = logging.getLogger(__name__)

def _srem_timeouts():
    """
    Render قد يقتل worker إذا طال الاتصال الخارجي.
    نستخدم (connect_timeout, read_timeout) ويمكن ضبطها عبر ENV.
    """
    connect = float(getattr(settings, "SREM_HTTP_CONNECT_TIMEOUT", 5) or 5)
    read = float(getattr(settings, "SREM_HTTP_READ_TIMEOUT", 15) or 15)
    return (connect, read)

def _build_retrying_session() -> requests.Session:
    """
    جلسة Requests مع Retry لتخفيف أعطال الشبكة على بيئات مثل Render.
    """
    session = requests.Session()
    retries_setting = getattr(settings, "SREM_HTTP_RETRIES", 0)
    retries = int(retries_setting) if retries_setting is not None else 0
    backoff_setting = getattr(settings, "SREM_HTTP_BACKOFF", 0.0)
    backoff = float(backoff_setting) if backoff_setting is not None else 0.0
    
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class SremClient:
    """
    عميل HTTP لـ API البورصة العقارية (وزارة العدل).
    الرابط: https://srem.moj.gov.sa — نفس النطاق المستخدم في المتصفح.
    """

    BASE = "https://prod-srem-api-srem.moj.gov.sa/api/v1/Dashboard"

    def __init__(self):
        self.session = _build_retrying_session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": "https://srem.moj.gov.sa",
                "Referer": "https://srem.moj.gov.sa/",
            }
        )

    def get_area_info(self, city_code: Optional[int] = None) -> Dict[str, Any]:
        """
        GetAreaInfo — إحصائيات حسب المنطقة/المدينة.
        city_code: رمز المدينة (مثلاً جدة 37528 كما في GetTrendingDistricts). إن مرّرت None يُؤخذ من الإعدادات.
        """
        code = (
            city_code
            if city_code is not None
            else int(getattr(settings, "SREM_JEDDAH_CITY_SERIAL", 37528))
        )

        url = f"{self.BASE}/GetAreaInfo"

        payload = {
            "periodCategory": "D",
            "period": 1,
            "areaSerial": 0,
            "areaType": "A",
            "cityCode": code,
        }

        try:
            response = self.session.post(url, json=payload, timeout=_srem_timeouts())
            response.raise_for_status()
            data = response.json()
            ok = bool(data.get("IsSuccess") or data.get("isSuccess"))
            if not ok:
                logger.warning("SREM GetAreaInfo IsSuccess=False payload=%s", data.get("Message") or data)
            return data
        except Exception as e:
            logger.exception("SREM GetAreaInfo failed: %s", e)
            return {}