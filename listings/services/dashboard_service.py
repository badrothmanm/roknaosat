import logging
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Sum, Exists, OuterRef, Value, F, Q
from django.db.models.functions import Coalesce
from django.contrib.auth.models import User
from listings.models import Property, PropertyRequest, PropertyOffer, PropertyLead, PropertyMatch, FastRequest, PropertySmartLink

logger = logging.getLogger(__name__)

# عناوين عربية لعمود «المصدر» في واجهة الداشبورد (يتطابق مع PropertyRequest.SOURCE_CHOICES)
_REQUEST_SOURCE_LABEL_AR = {
    "website": "الموقع",
    "ai_chat": "المساعد الذكي",
    "whatsapp": "واتساب",
    "manual": "يدوي",
}

# حقول أُضيفت في هجرات 0057 / 0058. استخدام defer يمنع إدراجها في SELECT —
# مفيد إن تأخّر تشغيل migrate على الإنتاج (خطأ: column … does not exist).
_PROPERTYREQUEST_DEFER_FIELDS = (
    "rooms",
    "furnished",
    "category",
    "conversation_id",
    "score",
    "priority",
)


def _propertyrequest_queryset():
    return PropertyRequest.objects.defer(*_PROPERTYREQUEST_DEFER_FIELDS)


class DashboardService:
    @staticmethod
    def get_dashboard_data(period: str = "all") -> dict:
        """
        Fetches all dashboard data directly from the database to ensure real-time data.
        """
        now = timezone.now()
        start_date = DashboardService._get_start_date(period, now)
        
        return {
            "kpis": DashboardService._get_kpis(start_date, now),
            "activity": DashboardService._get_activity_streams(),
            "ai_insights": DashboardService._get_ai_insights(start_date),
            "period": period,
        }

    @staticmethod
    def _get_start_date(period: str, now: timezone.datetime):
        if period == "today":
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "7days":
            return now - timedelta(days=7)
        elif period == "30days":
            return now - timedelta(days=30)
        elif period == "6months":
            return now - timedelta(days=30 * 6)
        elif period == "1year":
            return now - timedelta(days=365)
        return None # "all"

    @staticmethod
    def _get_kpis(start_date, now):
        """Calculates KPI metrics with basic trend approximations."""
        properties_qs = Property.objects.all()
        requests_qs = _propertyrequest_queryset()
        offers_qs = PropertyOffer.objects.all()
        matches_qs = PropertyMatch.objects.all()
        fast_requests_qs = FastRequest.objects.all()
        
        if start_date:
            properties_count = properties_qs.filter(created_at__gte=start_date).count()
            requests_count = requests_qs.filter(created_at__gte=start_date).count()
            offers_count = offers_qs.filter(created_at__gte=start_date).count()
            matches_count = matches_qs.filter(created_at__gte=start_date).count()
            fast_requests_count = fast_requests_qs.filter(created_at__gte=start_date).count()
            
            # Simple trend calculation
            period_duration = now - start_date
            prev_start = start_date - period_duration
            
            prev_properties = properties_qs.filter(created_at__gte=prev_start, created_at__lt=start_date).count()
            prev_requests = requests_qs.filter(created_at__gte=prev_start, created_at__lt=start_date).count()
            prev_fast_requests = fast_requests_qs.filter(created_at__gte=prev_start, created_at__lt=start_date).count()
        else:
            properties_count = properties_qs.count()
            requests_count = requests_qs.count()
            offers_count = offers_qs.count()
            matches_count = matches_qs.count()
            fast_requests_count = fast_requests_qs.count()
            prev_properties, prev_requests, prev_fast_requests = 0, 0, 0
            
        def calculate_trend(current, prev):
            if prev == 0:
                return "↑ 100%" if current > 0 else "0%"
            change = ((current - prev) / prev) * 100
            if change > 0:
                return f"↑ {change:.1f}%"
            elif change < 0:
                return f"↓ {abs(change):.1f}%"
            return "0%"

        return {
            "total_properties": properties_count,
            "properties_trend": calculate_trend(properties_count, prev_properties) if start_date else "",
            "new_requests": requests_count,
            "requests_trend": calculate_trend(requests_count, prev_requests) if start_date else "",
            "fast_requests": fast_requests_count,
            "fast_requests_trend": calculate_trend(fast_requests_count, prev_fast_requests) if start_date else "",
            "new_offers": offers_count,
            "smart_matches": matches_count,
        }

    @staticmethod
    def _get_activity_streams():
        """Fetches the latest activities for the dashboard."""
        recent_offers = [
            {
                "id": o.id,
                "name": o.owner_name,
                "phone": o.phone,
                "created_at": timezone.localtime(o.created_at).strftime("%d/%m %H:%M"),
                "status": o.status,
            }
            for o in PropertyOffer.objects.order_by("-created_at")[:5]
        ]
        recent_requests = [
             {
                "id": r.id,
                "name": r.name,
                "property_type": r.property_type,
                "district": r.district,
                "city": r.city,
                "created_at": timezone.localtime(r.created_at).strftime("%d/%m %H:%M"),
                "status": r.status,
                "source": getattr(r, "source", None) or "website",
                "source_label_ar": _REQUEST_SOURCE_LABEL_AR.get(
                    getattr(r, "source", None) or "website",
                    "—",
                ),
            }
            for r in _propertyrequest_queryset().order_by("-created_at")[:5]
        ]
        recent_leads = [
            {
                "id": l.id,
                "name": l.name,
                "phone": l.phone,
                "created_at": timezone.localtime(l.created_at).strftime("%d/%m %H:%M"),
                "status": l.status if hasattr(l, 'status') else "new",
            }
            for l in PropertyLead.objects.order_by("-created_at")[:5]
        ]
        return {
            "offers": recent_offers,
            "requests": recent_requests,
            "leads": recent_leads
        }

    @staticmethod
    def _fmt_pct(value):
        """تنسيق نسبة مئوية؛ None أو غير محدد → شرطة."""
        if value is None:
            return "—"
        try:
            v = float(value)
        except (TypeError, ValueError):
            return "—"
        if v != v:  # NaN
            return "—"
        v = max(0.0, min(100.0, v))
        return f"{round(v)}%"

    @staticmethod
    def _get_ai_insights(start_date):
        """
        مؤشرات مبنية على بيانات فعلية في النطاق الزمني المختار.
        - احتمالية الإغلاق: نسبة طلبات العقار بحالة «تمت المطابقة» أو «مغلق» من إجمالي الطلبات.
        - نسبة النجاح المتوقعة: نسبة العملاء «المهتمين» من إجمالي العملاء المحتملين؛
          إن لم يوجد عملاء في النطاق: نسبة الطلبات التي لديها مطابقة واحدة على الأقل.
        """
        requests_qs = _propertyrequest_queryset()
        leads_qs = PropertyLead.objects.all()

        if start_date:
            requests_qs = requests_qs.filter(created_at__gte=start_date)
            leads_qs = leads_qs.filter(created_at__gte=start_date)

        total_requests = requests_qs.count()

        # طلبات وصلت لمرحلة إغلاق/مطابقة (حسب الحقول المعرفة في النموذج)
        closed_like = requests_qs.filter(status__in=["matched", "closed"]).count()

        if total_requests > 0:
            closing_pct = 100.0 * closed_like / total_requests
        else:
            closing_pct = None

        # طلبات لديها مطابقة (للاستخدام عند غياب leads)
        has_match = Exists(
            PropertyMatch.objects.filter(request_id=OuterRef("pk"))
        )
        requests_with_match = requests_qs.filter(has_match).count()

        total_leads = leads_qs.count()
        if total_leads > 0:
            interested = leads_qs.filter(
                status=PropertyLead.Status.INTERESTED
            ).count()
            success_pct = 100.0 * interested / total_leads
        elif total_requests > 0:
            success_pct = 100.0 * requests_with_match / total_requests
        else:
            success_pct = None

        top_areas = (
            requests_qs.exclude(district__isnull=True)
            .exclude(district__exact="")
            .exclude(district__exact="غير محدد")
            .values("district")
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )
        top_areas_list = [{"name": area["district"], "count": area["count"]} for area in top_areas]

        # تفاعل: استفسارات العقار + مجموع مشاهدات الروابط الذكية
        most_viewed = (
            Property.objects.annotate(
                link_views=Coalesce(Sum("smart_links__views"), Value(0)),
            )
            .annotate(engagement=F("inquiry_count") + F("link_views"))
            .order_by("-engagement", "-inquiry_count")[:5]
        )
        most_viewed_list = [
            {
                "id": p.id,
                "title": f"{p.property_type} - {p.district}",
                "views": int(p.engagement),
            }
            for p in most_viewed
        ]

        return {
            "top_areas": top_areas_list,
            "most_viewed": most_viewed_list,
            "closing_probability": DashboardService._fmt_pct(closing_pct),
            "success_rate": DashboardService._fmt_pct(success_pct),
            "closing_probability_raw": closing_pct,
            "success_rate_raw": success_pct,
            "meta": {
                "requests_in_period": total_requests,
                "requests_matched_or_closed": closed_like,
                "requests_with_any_match": requests_with_match,
                "leads_in_period": total_leads,
            },
        }

    @staticmethod
    def get_marketer_stats(marketer_id: int, period: str = "all") -> dict:
        """
        Calculates statistics and fetches detailed lists for a specific marketer.
        """
        now = timezone.now()
        start_date = DashboardService._get_start_date(period, now)
        
        from django.urls import reverse
        from listings.models import Property, PropertyRequest, PropertyLead, FastRequest
        
        # 1. Links stats
        links_qs = PropertySmartLink.objects.filter(marketer_id=marketer_id)
        if start_date:
            links_qs = links_qs.filter(created_at__gte=start_date)
        
        total_links = links_qs.count()
        total_views = sum(links_qs.values_list('views', flat=True))
        
        # 2. Leads stats
        leads_qs = PropertyLead.objects.filter(smart_link__marketer_id=marketer_id)
        fast_requests_qs = FastRequest.objects.filter(
            Q(smart_link__marketer_id=marketer_id) | Q(assigned_to_id=marketer_id)
        )
        
        if start_date:
            leads_qs = leads_qs.filter(created_at__gte=start_date)
            fast_requests_qs = fast_requests_qs.filter(created_at__gte=start_date)
            
        total_leads = leads_qs.count() + fast_requests_qs.count()
        
        # 3. Conversion Rate
        conversion_rate = 0
        if total_views > 0:
            conversion_rate = (total_leads / total_views) * 100

        # 4. مهام مسندة: طلبات بحث عن عقار + طلبات تسويق عقار
        assigned_req_qs = _propertyrequest_queryset().filter(assigned_to_id=marketer_id)
        assigned_offer_qs = PropertyOffer.objects.filter(assigned_to_id=marketer_id)
        assigned_tasks_total = assigned_req_qs.count() + assigned_offer_qs.count()

        merged = []
        for r in assigned_req_qs:
            merged.append({
                "kind_label": "بحث عن عقار",
                "name": r.name,
                "phone": r.phone,
                "detail": f"{r.property_type} — {r.district}",
                "status": r.get_status_display(),
                "created_at": timezone.localtime(r.created_at).strftime("%d/%m %H:%M"),
                "sort_ts": r.created_at,
                "change_url": reverse("admin:listings_propertyrequest_change", args=[r.pk]),
            })
        for o in assigned_offer_qs:
            merged.append({
                "kind_label": "تسويق عقار",
                "name": o.owner_name or "—",
                "phone": o.phone or "—",
                "detail": f"{o.city or '—'} — {o.neighborhood or '—'} · {o.property_type or '—'}",
                "status": o.get_status_display(),
                "created_at": timezone.localtime(o.created_at).strftime("%d/%m %H:%M"),
                "sort_ts": o.created_at,
                "change_url": reverse("admin:listings_propertyoffer_change", args=[o.pk]),
            })
        merged.sort(key=lambda x: x["sort_ts"], reverse=True)
        assigned_tasks = [
            {k: v for k, v in row.items() if k != "sort_ts"}
            for row in merged[:15]
        ]

        # 5. Properties list
        properties = Property.objects.filter(visibility='منشور').order_by('-created_at')[:50]
        marketer_links = {l.property_id: {'token': l.token, 'views': l.views, 'inquiries': l.inquiry_count} for l in PropertySmartLink.objects.filter(marketer_id=marketer_id)}
        
        available_properties = []
        for p in properties:
            link_data = marketer_links.get(p.id, {})
            available_properties.append({
                "id": p.id,
                "listing_id": p.listing_id,
                "title": f"{p.property_type} - {p.district}",
                "district": p.district,
                "property_type": p.property_type,
                "offer_type": p.offer_type,
                "area": float(p.area),
                "price": float(p.price),
                "rooms": p.rooms,
                "bathrooms": p.bathrooms,
                "has_link": p.id in marketer_links,
                "token": link_data.get('token'),
                "views": link_data.get('views', 0),
                "inquiries": link_data.get('inquiries', 0),
                "view_url": p.get_absolute_url()
            })

        # 6. General Link
        general_link = f"/?m={marketer_id}"

        return {
            "total_links": total_links,
            "total_views": total_views,
            "total_leads": total_leads,
            "conversion_rate": f"{conversion_rate:.1f}%",
            "assigned_tasks": assigned_tasks,
            "assigned_tasks_total": assigned_tasks_total,
            "available_properties": available_properties,
            "general_link": general_link,
            "period": period
        }
    @staticmethod
    def get_marketers_overview(period: str = "all") -> dict:
        """
        Calculates aggregate statistics for all marketers to allow admin monitoring.
        """
        from django.contrib.auth.models import User
        from django.conf import settings as dj_settings
        from django.db.models import Sum, Q
        from listings.utils.marketer_ordering import annotate_staff_marketer_sort

        now = timezone.now()
        start_date = DashboardService._get_start_date(period, now)

        # staff: ترتيب المدير (badr9090) ثم المسوّق المرجعي الأول (b1) ثم البقية
        mq = User.objects.filter(is_staff=True)
        marketers = annotate_staff_marketer_sort(mq, dj_settings)
        
        overview_data = []
        total_team_views = 0
        total_team_leads = 0
        total_team_links = 0
        
        for m in marketers:
            # Stats for this marketer
            links_qs = PropertySmartLink.objects.filter(marketer=m)
            leads_qs = PropertyLead.objects.filter(smart_link__marketer=m)
            fast_qs = FastRequest.objects.filter(smart_link__marketer=m)
            assigned_qs = _propertyrequest_queryset().filter(assigned_to=m)
            
            if start_date:
                links_qs = links_qs.filter(created_at__gte=start_date)
                leads_qs = leads_qs.filter(created_at__gte=start_date)
                fast_qs = fast_qs.filter(created_at__gte=start_date)
            
            m_links = links_qs.count()
            counts = links_qs.aggregate(total_views=Sum('views'), total_inquiries=Sum('inquiry_count'))
            m_views = counts['total_views'] or 0
            m_inquiries = counts['total_inquiries'] or 0
            
            # Note: m_leads counts lead objects, which might differ from inquiry_count if old data exists
            m_leads = leads_qs.count() + fast_qs.count()
            
            # Tasks breakdown
            tasks_new = assigned_qs.filter(status='new').count()
            tasks_working = assigned_qs.filter(status='working').count()
            tasks_done = assigned_qs.filter(status='closed').count()
            
            conv_rate = (m_leads / m_views * 100) if m_views > 0 else 0
            
            overview_data.append({
                "user": m,
                "links": m_links,
                "views": m_views,
                "inquiries": m_inquiries,
                "leads": m_leads,
                "conv_rate": f"{conv_rate:.1f}%",
                "tasks": {
                    "new": tasks_new,
                    "working": tasks_working,
                    "done": tasks_done,
                    "total": assigned_qs.count()
                }
            })
            
            total_team_views += m_views
            total_team_leads += m_leads
            total_team_links += m_links

        team_conv_rate = (total_team_leads / total_team_views * 100) if total_team_views > 0 else 0
        
        return {
            "marketers": overview_data,
            "team_stats": {
                "total_views": total_team_views,
                "total_leads": total_team_leads,
                "total_links": total_team_links,
                "avg_conv_rate": f"{team_conv_rate:.1f}%"
            },
            "period": period
        }

    @staticmethod
    def get_offer_header_stats() -> dict:
        """
        Fetches summary stats for the PropertyOffer dashboard header.
        """
        from listings.models import PropertyOffer
        from django.utils import timezone
        from datetime import timedelta
        
        total = PropertyOffer.objects.count()
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        new_today = PropertyOffer.objects.filter(created_at__gte=today_start).count()
        
        # New statuses
        contacted = PropertyOffer.objects.filter(status=PropertyOffer.Status.CONTACTED).count()
        under_review = PropertyOffer.objects.filter(status=PropertyOffer.Status.UNDER_REVIEW).count()
        owner_review = PropertyOffer.objects.filter(status=PropertyOffer.Status.OWNER_REVIEW).count()
        published = PropertyOffer.objects.filter(status=PropertyOffer.Status.PUBLISHED).count()

        return {
            "total": total,
            "new_today": new_today,
            "contacted": contacted,
            "under_review": under_review,
            "owner_review": owner_review,
            "published": published,
        }

    @staticmethod
    def get_request_header_stats() -> dict:
        """
        Fetches summary stats for the PropertyRequest dashboard header.
        """
        from django.utils import timezone

        total = _propertyrequest_queryset().count()
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        new_today = _propertyrequest_queryset().filter(created_at__gte=today_start).count()

        working = _propertyrequest_queryset().filter(status="working").count()
        contacted = _propertyrequest_queryset().filter(status="contacted").count()
        matched = _propertyrequest_queryset().filter(status="matched").count()

        return {
            "total": total,
            "new_today": new_today,
            "working": working,
            "contacted": contacted,
            "matched": matched,
        }

    @staticmethod
    def get_property_header_stats() -> dict:
        """
        Fetches summary stats for the Property dashboard header.
        """
        from listings.models import Property
        from django.utils import timezone
        
        total = Property.objects.count()
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        new_today = Property.objects.filter(created_at__gte=today_start).count()
        
        published = Property.objects.filter(visibility='منشور').count()
        private = Property.objects.filter(visibility='خاص').count()
        archived = Property.objects.filter(visibility='مؤرشف').count()

        return {
            "total": total,
            "new_today": new_today,
            "published": published,
            "private": private,
            "archived": archived,
        }

    @staticmethod
    def get_lead_header_stats() -> dict:
        """
        Fetches summary stats for the PropertyLead dashboard header.
        """
        from listings.models import PropertyLead
        from django.utils import timezone
        
        total = PropertyLead.objects.count()
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        new_today = PropertyLead.objects.filter(created_at__gte=today_start).count()
        
        interested = PropertyLead.objects.filter(status=PropertyLead.Status.INTERESTED).count()
        not_interested = PropertyLead.objects.filter(status=PropertyLead.Status.NOT_INTERESTED).count()
        neutral = PropertyLead.objects.filter(status=PropertyLead.Status.NEUTRAL).count()
        special = PropertyLead.objects.filter(status=PropertyLead.Status.SPECIAL_REQUEST).count()

        return {
            "total": total,
            "new_today": new_today,
            "interested": interested,
            "not_interested": not_interested,
            "neutral": neutral,
            "special": special,
        }
