"""
listings/services/matching.py
============================
Weighted Scoring Matching Engine for PropertyRequest ↔ Property.

**Scoring model (normalized):** final score = Σ (w_i × c_i) where each c_i ∈ [0,1] and Σ w_i = 1.
Interpretation: ~0.9 very strong, ~0.6 acceptable (thresholds THRESHOLD_CANDIDATE / HIGH unchanged).

Candidates: منشور + متاح + نفس نوع العقار + حي (iexact) + فلتر سعر عند وجود ميزانية ±30%.
بدون ميزانية: فلترة ناعمة حول وسيط أسعار دفعة المرشحين + مكوّن سعر يعتمد على القرب من الوسيط.

Performance: كاش سلوك لكل جوال، حد MAX_CANDIDATES، حفظ أعلى MAX_MATCHES_TO_PERSIST مطابقة.
"""

from __future__ import annotations

import logging
import math
import re
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

# ── أوزان افتراضية (مجموعها 1.0) — تُضبط من PROPERTY_MATCHING
_DEFAULT_NORM_WEIGHTS: Dict[str, float] = {
    # مجموع 1.0 — عند تطابق كامل لجميع المكوّنات تكون النتيجة 1.0
    "W_TYPE": 0.33,
    "W_DISTRICT": 0.28,
    "W_BUDGET": 0.27,
    "W_BEHAVIOR": 0.06,
    "W_AREA": 0.02,
    "W_ROOMS": 0.02,
    "W_AGE": 0.02,
}


def _get_matching_config():
    """Read matching config; includes normalized weights (sum ≈ 1)."""
    conf = getattr(settings, "PROPERTY_MATCHING", None) or {}
    base = {
        "THRESHOLD_CANDIDATE": conf.get("THRESHOLD_CANDIDATE", 0.6),
        "THRESHOLD_HIGH_MATCH": conf.get("THRESHOLD_HIGH_MATCH", 0.8),
        "BUDGET_EXACT_RATIO": conf.get("BUDGET_EXACT_RATIO", 0.20),
        "BUDGET_LOOSE_RATIO": conf.get("BUDGET_LOOSE_RATIO", 0.30),
        "MAX_CANDIDATES": conf.get("MAX_CANDIDATES", 500),
        "MAX_MATCHES_TO_PERSIST": conf.get("MAX_MATCHES_TO_PERSIST", 10),
        "REVERSE_MATCH_MAX_REQUESTS": conf.get("REVERSE_MATCH_MAX_REQUESTS", 1000),
        "DISTRICT_GROUPS": conf.get("DISTRICT_GROUPS"),
        # فلترة ناعمة بدون ميزانية: حول وسيط أسعار المرشحين
        "NO_BUDGET_BAND_LOW": float(conf.get("NO_BUDGET_BAND_LOW", 0.35)),
        "NO_BUDGET_BAND_HIGH": float(conf.get("NO_BUDGET_BAND_HIGH", 2.8)),
        "NO_BUDGET_LOG_SIGMA": float(conf.get("NO_BUDGET_LOG_SIGMA", 0.55)),
        # مطابقة حي تقريبية (SequenceMatcher)
        "DISTRICT_FUZZY_HIGH": float(conf.get("DISTRICT_FUZZY_HIGH", 0.88)),
        "DISTRICT_FUZZY_LOW": float(conf.get("DISTRICT_FUZZY_LOW", 0.72)),
    }
    base["NORM_WEIGHTS"] = _resolve_norm_weights(conf)
    # توافق قديم مع أسماء WEIGHT_* المكدسة
    for k in (
        "WEIGHT_TYPE",
        "WEIGHT_DISTRICT",
        "WEIGHT_BUDGET",
        "WEIGHT_AREA",
        "WEIGHT_ROOMS",
        "WEIGHT_BEHAVIOR",
        "WEIGHT_PROPERTY_AGE",
    ):
        base[k] = conf.get(k)
    return base


def _resolve_norm_weights(conf: dict) -> Dict[str, float]:
    """
    يبني قاموس أوزان موزّع على 1.0.
    يدعم المفاتيح الجديدة W_* أو يشتق من WEIGHT_* القديمة.
    """
    if conf.get("NORM_WEIGHTS") and isinstance(conf["NORM_WEIGHTS"], dict):
        w = {k: float(v) for k, v in conf["NORM_WEIGHTS"].items()}
        s = sum(w.values())
        if s > 1e-9:
            return {k: w[k] / s for k in w}

    if any(conf.get(f"W_{x}") is not None for x in ("TYPE", "DISTRICT", "BUDGET")):
        w = {}
        for k, dk in _DEFAULT_NORM_WEIGHTS.items():
            w[k] = float(conf.get(k, dk))
        s = sum(w.values())
        if s > 1e-9:
            return {k: w[k] / s for k in w}

    # اشتقاق من الأوزان المكدسة القديمة ثم تطبيع
    legacy = {
        "W_TYPE": float(conf.get("WEIGHT_TYPE", 0.40)),
        "W_DISTRICT": float(conf.get("WEIGHT_DISTRICT", 0.30)),
        "W_BUDGET": float(conf.get("WEIGHT_BUDGET", 0.30)),
        "W_BEHAVIOR": float(conf.get("WEIGHT_BEHAVIOR", 0.15)),
        "W_AREA": float(conf.get("WEIGHT_AREA", 0.05)),
        "W_ROOMS": float(conf.get("WEIGHT_ROOMS", 0.05)),
        "W_AGE": float(conf.get("WEIGHT_PROPERTY_AGE", 0.03)),
    }
    s = sum(legacy.values())
    if s <= 1e-9:
        legacy = dict(_DEFAULT_NORM_WEIGHTS)
        s = sum(legacy.values())
    return {k: legacy[k] / s for k in legacy}


# ── تطبيع نصوص الأحياء (عربي) ──


def _normalize_district(value: Optional[str]) -> str:
    """توافق خلفي: مسافات + lower (لاتيني)."""
    if value is None:
        return ""
    return str(value).strip().lower()


_AR_EQUIV = (
    ("أ", "ا"),
    ("إ", "ا"),
    ("آ", "ا"),
    ("ٱ", "ا"),
    ("ى", "ي"),
    ("ة", "ه"),
)


def normalize_district_ar(value: Optional[str]) -> str:
    """
    تطبيع أقوى للمقارنة: إزالة المسافات والتطويل، توحيد أشكال الألف/الألف المقصورة/التاء المربوطة.
    """
    if value is None:
        return ""
    s = re.sub(r"[\u0640\u200c\u200f\s]+", "", str(value).strip())
    for a, b in _AR_EQUIV:
        s = s.replace(a, b)
    return s.casefold()


def _district_group_match(
    norm_req_ar: str,
    norm_prop_ar: str,
    district_groups: Optional[dict],
) -> bool:
    if not norm_req_ar or not norm_prop_ar or not district_groups:
        return False
    for group_key, aliases in district_groups.items():
        if not isinstance(aliases, (list, tuple)):
            continue
        keys_norm = [
            normalize_district_ar(g) for g in [group_key] + list(aliases)
        ]
        if norm_req_ar in keys_norm and norm_prop_ar in keys_norm:
            return True
    return False


def _district_component_score(
    request_district: Optional[str],
    prop_district: Optional[str],
    district_groups: Optional[dict],
    fuzzy_high: float,
    fuzzy_low: float,
) -> float:
    """
    مكوّن حي ∈ [0,1]: تطابق مجموعات = 1، تطابق تام بعد التطبيع = 1، تشابه جزئي،否则 0.
    """
    ra = normalize_district_ar(request_district)
    pa = normalize_district_ar(prop_district)
    if not ra or not pa:
        return 0.0
    if _district_group_match(ra, pa, district_groups):
        return 1.0
    if ra == pa:
        return 1.0
    ratio = SequenceMatcher(None, ra, pa).ratio()
    if ratio >= fuzzy_high:
        return 0.88 + 0.12 * (ratio - fuzzy_high) / max(1e-9, 1.0 - fuzzy_high)
    if ratio >= fuzzy_low:
        return 0.55 + 0.33 * (ratio - fuzzy_low) / max(1e-9, fuzzy_high - fuzzy_low)
    return 0.0


def _parse_area(value: Optional[str]) -> Optional[Decimal]:
    if value is None or not str(value).strip():
        return None
    s = re.sub(r"\s+", "", str(value).strip())
    s = s.replace(",", ".")
    if not s:
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _parse_rooms(value: Optional[str]) -> Optional[int]:
    if value is None or not str(value).strip():
        return None
    s = re.sub(r"\D", "", str(value).strip())
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _request_room_int(request) -> Optional[int]:
    r = getattr(request, "rooms", None)
    if r is not None:
        try:
            ri = int(r)
            if 0 <= ri <= 100:
                return ri
        except (TypeError, ValueError):
            pass
    return _parse_rooms(getattr(request, "rooms_count", None))


def _normalize_age_token(value: Optional[str]) -> str:
    if value is None or not str(value).strip():
        return ""
    return re.sub(r"\s+", "", str(value).strip().lower())


def _median(values: List[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def _component_budget_with_reference(
    price: float,
    budget: Optional[float],
    reference_median: Optional[float],
    config: dict,
) -> float:
    """
    مكوّن ميزانية/سعر ∈ [0,1].
    - مع ميزانية: انحراف نسبي مع منحدر ناعم بعد BUDGET_LOOSE_RATIO.
    - بدون ميزانية: قرب السعر من reference_median (وسيط الدفعة) على مقياس لوغاريتمي.
    - بدون مرجع (مسار عكسي): حياد 0.75 حتى لا يُلغى الطرف الآخر.
    """
    exact = float(config["BUDGET_EXACT_RATIO"])
    loose = float(config["BUDGET_LOOSE_RATIO"])
    sigma = float(config["NO_BUDGET_LOG_SIGMA"])

    if budget is not None and budget > 0:
        r = abs(price - budget) / budget
        if r <= exact:
            return 1.0
        if r <= loose:
            return 0.65 + 0.35 * (loose - r) / max(1e-9, loose - exact)
        # انحدار نحو 0 عند انحرافات كبيرة (لا يزال يمكن أن يمرّ بحد 0.6 إن وُجدت مكونات أخرى)
        tail = (r - loose) / max(1e-9, 1.0 - loose)
        return max(0.0, 0.35 * (1.0 - min(1.0, tail)))

    if reference_median is not None and reference_median > 0 and price > 0:
        d = abs(math.log(price) - math.log(reference_median))
        return max(0.0, min(1.0, math.exp(-d / max(1e-9, sigma))))

    return 0.75


def _component_area(req_area: Optional[Decimal], prop_area) -> float:
    if req_area is None or req_area <= 0 or prop_area is None:
        return 0.0
    try:
        pa = Decimal(str(prop_area))
        if pa <= 0:
            return 0.0
        ratio = min(pa, req_area) / max(pa, req_area)
        if ratio >= Decimal("0.9"):
            return 1.0
        if ratio >= Decimal("0.7"):
            return 0.55
        return 0.25
    except (InvalidOperation, TypeError, ZeroDivisionError):
        return 0.0


def _component_rooms(req_rooms: Optional[int], prop_rooms: Optional[int]) -> float:
    if req_rooms is None or prop_rooms is None:
        return 0.0
    try:
        pr = int(prop_rooms)
        d = abs(pr - req_rooms)
        if d == 0:
            return 1.0
        if d == 1:
            return 0.55
        if d == 2:
            return 0.25
        return 0.0
    except (TypeError, ValueError):
        return 0.0


class BaseMatchingEngine:
    def match_request(self, request) -> List:
        raise NotImplementedError


class PropertyMatcher(BaseMatchingEngine):
    """
    مطابقة موزّعة على [0,1] مع Σ أوزان = 1.
    """

    def _config(self):
        return _get_matching_config()

    def _get_behavior_score(self, request) -> float:
        cache = getattr(self, "_behavior_score_cache", None)
        phone = getattr(request, "phone", None) or ""
        if cache is None:
            return self._calculate_behavioral_score(request)
        if phone not in cache:
            cache[phone] = self._calculate_behavioral_score(request)
        return cache[phone]

    def match_request(self, request) -> List:
        self._behavior_score_cache = {}
        self._no_budget_median_price: Optional[float] = None
        self._reverse_mode = False
        try:
            return self._match_request_impl(request)
        finally:
            self._behavior_score_cache = None
            self._no_budget_median_price = None

    def _apply_no_budget_soft_filter(
        self,
        candidates: List,
        config: dict,
    ) -> List:
        """بدون ميزانية: إزالة أسعار شديدة الابتعاد عن وسيط الدفعة."""
        if len(candidates) <= 1:
            if candidates:
                self._no_budget_median_price = float(candidates[0].price)
            return candidates
        prices = [float(p.price) for p in candidates if p.price is not None]
        if not prices:
            return candidates
        med = _median(prices)
        self._no_budget_median_price = med
        lo = med * float(config["NO_BUDGET_BAND_LOW"])
        hi = med * float(config["NO_BUDGET_BAND_HIGH"])
        out = [p for p in candidates if p.price is not None and lo <= float(p.price) <= hi]
        if out:
            return out
        return candidates

    def _match_request_impl(self, request) -> List:
        from listings.models import Property, PropertyMatch, PropertyRequest

        config = self._config()
        max_candidates = config["MAX_CANDIDATES"]
        max_to_persist = max(1, int(config.get("MAX_MATCHES_TO_PERSIST", 10)))
        request_district_normalized = _normalize_district(request.district)

        base_filter = {
            "visibility": "منشور",
            "status": "متاح",
            "property_type": request.property_type,
        }
        if request_district_normalized:
            base_filter["district__iexact"] = (request.district or "").strip()

        has_budget = request.budget is not None
        try:
            budget_decimal = Decimal(str(request.budget)) if has_budget else None
        except (InvalidOperation, TypeError, ValueError):
            budget_decimal = None
            has_budget = False

        qs = (
            Property.objects.filter(**base_filter).only(
                "id",
                "listing_id",
                "property_type",
                "district",
                "price",
                "area",
                "rooms",
                "property_age",
                "created_at",
            )
        )

        if has_budget and budget_decimal is not None and budget_decimal > 0:
            lower_bound = budget_decimal * Decimal("0.70")
            upper_bound = budget_decimal * Decimal("1.30")
            qs = qs.filter(price__gte=lower_bound, price__lte=upper_bound)

        qs = qs.order_by("-created_at")[:max_candidates]
        candidates = list(qs)

        if not has_budget and candidates:
            candidates = self._apply_no_budget_soft_filter(candidates, config)

        if not candidates:
            logger.info(
                "[Matcher] No candidates for request #%s (%s / %s / budget=%s)",
                request.id,
                request.property_type,
                request.district,
                request.budget,
            )
            return []

        scored = []
        for prop in candidates:
            score = self._calculate_score(request, prop, config)
            if score >= config["THRESHOLD_CANDIDATE"]:
                scored.append((prop, score))

        if not scored:
            logger.info("[Matcher] No candidate met threshold for request #%s", request.id)
            return []

        scored.sort(key=lambda x: x[1], reverse=True)
        scored = scored[:max_to_persist]

        created_matches = []
        with transaction.atomic():
            from listings.models import PropertyMatch as PM

            PM.objects.filter(request=request).delete()

            for prop, score in scored:
                match = PM.objects.create(
                    request=request,
                    property=prop,
                    score=round(min(score, 1.0), 4),
                )
                created_matches.append(match)

            best_score = scored[0][1]
            new_status = (
                "matched" if best_score >= config["THRESHOLD_HIGH_MATCH"] else request.status
            )
            final_score = round(min(best_score, 1.0), 4)

            PropertyRequest.objects.filter(pk=request.pk).update(
                match_score=final_score,
                matched_count=len(created_matches),
                status=new_status,
            )
            request.match_score = final_score
            request.matched_count = len(created_matches)
            request.status = new_status

        logger.info(
            "[Matcher] Request #%s → %d matches, best score=%.2f, status=%s",
            request.id,
            len(created_matches),
            final_score,
            new_status,
        )
        return created_matches

    def _calculate_score(self, request, prop, config: Optional[dict] = None) -> float:
        if config is None:
            config = self._config()
        w = config["NORM_WEIGHTS"]

        # 1) نوع العقار
        c_type = 1.0 if prop.property_type == request.property_type else 0.0

        # 2) حي
        c_dist = _district_component_score(
            request.district,
            prop.district,
            config["DISTRICT_GROUPS"],
            float(config["DISTRICT_FUZZY_HIGH"]),
            float(config["DISTRICT_FUZZY_LOW"]),
        )

        # 3) ميزانية / سعر
        has_budget = request.budget is not None
        try:
            bd = float(request.budget) if has_budget else None
        except (TypeError, ValueError):
            bd = None
        budget_for_formula = bd if bd and bd > 0 else None
        ref_median = getattr(self, "_no_budget_median_price", None)
        # بدون ميزانية: قرب من وسيط الدفعة (أمامي) أو حياد 0.75 (عكسي)
        if budget_for_formula is not None:
            ref_for_soft = None
        elif getattr(self, "_reverse_mode", False):
            ref_for_soft = None
        else:
            ref_for_soft = ref_median
        c_budget = _component_budget_with_reference(
            float(prop.price),
            budget_for_formula,
            ref_for_soft,
            config,
        )

        # 4) سلوك
        c_beh = self._get_behavior_score(request)

        # 5) مساحة
        req_area = _parse_area(getattr(request, "area", None))
        c_area = _component_area(req_area, getattr(prop, "area", None))

        # 6) غرف
        rr = _request_room_int(request)
        c_rooms = _component_rooms(rr, getattr(prop, "rooms", None))

        # 7) عمر
        ra = _normalize_age_token(getattr(request, "property_age", None))
        pa = _normalize_age_token(getattr(prop, "property_age", None))
        if ra and pa:
            if ra == pa:
                c_age = 1.0
            elif ra in pa or pa in ra:
                c_age = 0.55
            else:
                c_age = 0.0
        else:
            c_age = 0.0

        score = (
            w["W_TYPE"] * c_type
            + w["W_DISTRICT"] * c_dist
            + w["W_BUDGET"] * c_budget
            + w["W_BEHAVIOR"] * c_beh
            + w["W_AREA"] * c_area
            + w["W_ROOMS"] * c_rooms
            + w["W_AGE"] * c_age
        )
        return max(0.0, min(1.0, score))

    def _calculate_behavioral_score(self, request) -> float:
        from listings.models import PropertyLead

        phone = getattr(request, "phone", None)
        if not phone:
            return 0.5

        past_leads = PropertyLead.objects.filter(phone=phone)
        total_leads = past_leads.count()

        if total_leads == 0:
            return 0.5

        motivation = 0.5
        interested_count = past_leads.filter(status=PropertyLead.Status.INTERESTED).count()
        special_count = past_leads.filter(status=PropertyLead.Status.SPECIAL_REQUEST).count()
        rejected_count = past_leads.filter(status=PropertyLead.Status.NOT_INTERESTED).count()

        if special_count > 0:
            motivation += 0.4
        elif interested_count > 0:
            motivation += 0.3

        if rejected_count > 0:
            motivation -= 0.2

        if total_leads > 3:
            motivation += 0.1

        return max(0.0, min(motivation, 1.0))

    def find_matching_requests(self, prop) -> List:
        config = self._config()
        max_requests = config.get("REVERSE_MATCH_MAX_REQUESTS", 1000)
        self._behavior_score_cache = {}
        self._reverse_mode = True
        self._no_budget_median_price = float(prop.price) if prop.price else None
        try:
            return self._find_matching_requests_impl(prop, config, max_requests)
        finally:
            self._behavior_score_cache = None
            self._reverse_mode = False
            self._no_budget_median_price = None

    def _find_matching_requests_impl(self, prop, config, max_requests) -> List:
        from listings.models import PropertyMatch, PropertyRequest

        prop_district_normalized = _normalize_district(prop.district)
        district_filter = {}
        if prop_district_normalized:
            district_filter["district__iexact"] = (prop.district or "").strip()

        open_requests = (
            PropertyRequest.objects.filter(
                property_type=prop.property_type,
                status__in=["new", "matched"],
                **district_filter,
            )
            .only(
                "id",
                "name",
                "phone",
                "property_type",
                "district",
                "budget",
                "match_score",
                "matched_count",
                "status",
                "area",
                "rooms_count",
                "rooms",
                "property_age",
            )
            .order_by("-created_at")[:max_requests]
        )

        created = []
        for req in open_requests:
            score = self._calculate_score(req, prop, config)
            if score < config["THRESHOLD_HIGH_MATCH"]:
                continue

            new_score = round(min(score, 1.0), 4)
            match, created_now = PropertyMatch.objects.get_or_create(
                request=req,
                property=prop,
                defaults={"score": new_score},
            )
            if created_now:
                PropertyRequest.objects.filter(pk=req.pk).update(
                    match_score=max(req.match_score, new_score),
                    matched_count=req.matched_count + 1,
                    status="matched",
                )

                self._create_match_notification(req, prop, new_score)

                created.append(match)
                logger.info(
                    "[ReverseMatch] Property %s matched Request #%s (score=%.2f)",
                    prop.listing_id,
                    req.id,
                    score,
                )
            else:
                match.score = new_score
                match.save(update_fields=["score"])
                PropertyRequest.objects.filter(pk=req.pk).update(
                    match_score=max(req.match_score, new_score),
                )

        return created

    def _create_match_notification(self, request, property, score):
        from listings.models import CRMNotification

        target_user = request.assigned_to
        if not target_user:
            from listings.utils.staff_users import get_primary_staff_user

            target_user = get_primary_staff_user()

        if not target_user:
            return

        title = f"🎯 مطابقة ذكية جديدة: {property.listing_id}"
        message = (
            f"تم العثور على عقار مطابق لطلب العميل ({request.name}) بنسبة {score*100:.0f}%.\n"
            f"العقار: {property.property_type} في {property.district}.\n"
            f"الميزانية المطلوبة: {request.budget or 'غير محددة'} ريال."
        )
        link = f"/admin/listings/propertyrequest/{request.id}/change/"

        CRMNotification.objects.create(
            user=target_user,
            title=title,
            message=message,
            link=link,
        )
        try:
            from listings.services.staff_email import (
                collect_marketer_emails,
                notify_staff_action,
            )

            notify_staff_action(
                f"مطابقة ذكية: {property.listing_id}",
                message,
                link_obj=request,
                marketer_emails=collect_marketer_emails(target_user),
            )
        except Exception as exc:
            logger.warning("تعذّر إرسال بريد مطابقة ذكية: %s", exc)
