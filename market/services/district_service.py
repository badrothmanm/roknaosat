from __future__ import annotations

import logging
from typing import Optional

import requests
from django.conf import settings
from django.db import transaction

from market.models import District

logger = logging.getLogger(__name__)

def _srem_timeouts():
    connect = float(getattr(settings, "SREM_HTTP_CONNECT_TIMEOUT", 5) or 5)
    read = float(getattr(settings, "SREM_HTTP_READ_TIMEOUT", 15) or 15)
    return (connect, read)


class DistrictService:

    URL = "https://prod-srem-api-srem.moj.gov.sa/api/v1/Dashboard/GetTrendingDistricts"

    HEADERS = {
        "Content-Type": "application/json",
        "Origin": "https://srem.moj.gov.sa",
        "Referer": "https://srem.moj.gov.sa/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    @classmethod
    def _payload_for_city(cls, city_serial: int) -> dict:
        return {
            "periodCategory": "D",
            "citySerial": city_serial,
            "areaCategory": "C",
            "areaSerial": city_serial,
        }

    @classmethod
    def fetch_trending_districts(cls, city_serial: Optional[int] = None) -> list:
        """
        أحياء ضمن مؤشر الترند للمدينة (أسماء حقيقية + إجمالي صفقة/مساحة/قيمة من البورصة).
        يُفضّل على GetAreaInfo عندما يعيد الأخير فقط «جميع المناطق» بشرائح ساعية مضللة.
        """
        code = city_serial
        if code is None:
            code = int(getattr(settings, "SREM_JEDDAH_CITY_SERIAL", 37528))
        try:
            # reuse retrying session from SremClient if available
            try:
                from market.services.srem_client import _build_retrying_session  # type: ignore
                session = _build_retrying_session()
                post = session.post
            except Exception:
                post = requests.post

            response = post(
                cls.URL,
                json=cls._payload_for_city(code),
                headers=cls.HEADERS,
                timeout=_srem_timeouts(),
            )

            if response.status_code != 200:
                logger.error("GetTrendingDistricts HTTP %s", response.status_code)
                return []

            data = response.json()

            ok = bool(data.get("IsSuccess") or data.get("isSuccess"))
            if not ok:
                logger.error(
                    "GetTrendingDistricts IsSuccess=False msg=%s",
                    data.get("Message") or data.get("message") or data,
                )
                return []

            raw = data.get("Data")
            districts = []
            if isinstance(raw, dict):
                districts = (
                    raw.get("TrendingDistrictsPerCity")
                    or raw.get("trendingDistrictsPerCity")
                    or []
                )
            elif isinstance(raw, list):
                districts = raw
            if not districts:
                logger.warning("GetTrendingDistricts: قائمة أحياء فارغة — Data=%s", type(raw).__name__)
            return districts if isinstance(districts, list) else []

        except Exception as e:
            logger.exception("GetTrendingDistricts: %s", e)
            return []

    @classmethod
    def fetch_jeddah_districts(cls):
        return cls.fetch_trending_districts(
            int(getattr(settings, "SREM_JEDDAH_CITY_SERIAL", 37528))
        )

    @classmethod
    def sync_jeddah_districts(cls):
        districts = cls.fetch_jeddah_districts()

        if not districts:
            print("❌ No districts fetched")
            return 0

        saved = 0

        with transaction.atomic():
            for d in districts:
                District.objects.update_or_create(
                    district_code=d["DistrictCode"],
                    defaults={
                        "name": d["DistrictName"],
                        "city_name": d["CityName"],
                        "city_code": d["CityCode"],
                        "region_name": d["RegionName"],
                        "total_deals": d["TotalCount"],
                        "total_price": d["TotalPrice"],
                        "total_area": d["TotalArea"],
                    }
                )
                saved += 1

        print(f"✅ Saved {saved} districts")
        return saved