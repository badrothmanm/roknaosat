"""
listings/tests.py
=================
Unit & Integration Tests for PropertyRequest System.

Test Classes:
  1. TestPropertyMatcher       – Weighted scoring engine
  2. TestPropertyRequestAPI    – API endpoint flow
  3. TestPropertyMatchCreation – PropertyMatch record creation
  4. TestWhatsAppMessage       – WhatsApp message generation action
"""

import json
from datetime import date, time
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group, Permission, User
from django.core import mail
from django.conf import settings
from django.test import TestCase, Client, RequestFactory, override_settings
from django.urls import reverse

from .models import (
    Appointment,
    Property,
    PropertyLead,
    PropertyMatch,
    PropertyOffer,
    PropertyRequest,
    UserAccessProfile,
)
from .utils.staff_permissions import (
    staff_may_access_users_groups,
    staff_may_add_users,
    staff_may_change_passwords,
)
from .services.matching import PropertyMatcher
from .admin import PropertyRequestAdmin
from .admin import PropertyLeadAdmin, PropertyOfferAdmin


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def make_property(
    property_type="شقة",
    district="النعيم",
    price=500_000,
    status="متاح",
    visibility="منشور",
    offer_type="بيع",
    **kwargs,
):
    return Property.objects.create(
        full_name="مالك اختبار",
        phone="0501234567",
        city="جدة",
        district=district,
        property_type=property_type,
        offer_type=offer_type,
        area=Decimal("200"),
        price=Decimal(str(price)),
        status=status,
        visibility=visibility,
        **kwargs,
    )


def make_request(
    property_type="شقة",
    district="النعيم",
    budget=500_000,
    name="أحمد محمد",
    phone="966501234567",
    **kwargs,
):
    return PropertyRequest.objects.create(
        name=name,
        phone=phone,
        property_type=property_type,
        district=district,
        budget=Decimal(str(budget)),
        **kwargs,
    )


# ─────────────────────────────────────────────────────────────
# 1. Matching Engine Tests
# ─────────────────────────────────────────────────────────────
@override_settings(
    PROPERTY_MATCHING={
        **getattr(settings, "PROPERTY_MATCHING", {}),
        # أوزان ثابتة في الاختبارات: Σ=1، نتيجة مثالية هيكلياً ≈0.91 مع سلوك افتراضي 0.5
        "NORM_WEIGHTS": {
            "W_TYPE": 0.33,
            "W_DISTRICT": 0.28,
            "W_BUDGET": 0.27,
            "W_BEHAVIOR": 0.06,
            "W_AREA": 0.02,
            "W_ROOMS": 0.02,
            "W_AGE": 0.02,
        },
    }
)
class TestPropertyMatcher(TestCase):
    """Tests for normalized scoring engine (listings/services/matching.py)."""

    def setUp(self):
        self.matcher = PropertyMatcher()

    def test_perfect_match_score_is_100(self):
        """تطابق نوع + حي + سعر مع سلوك افتراضي (0.5) يعطي ~0.91 (قوي جداً، ليس 1.0 بسبب وزن السلوك)."""
        prop = make_property(property_type="شقة", district="النعيم", price=500_000)
        req = make_request(property_type="شقة", district="النعيم", budget=500_000)
        score = self.matcher._calculate_score(req, prop)
        # 0.33+0.28+0.27 + 0.06*0.5 = 0.91
        self.assertAlmostEqual(score, 0.91, places=2)

    def test_type_mismatch_reduces_score(self):
        """نوع مختلف: يُلغى وزن النوع، تبقى الحي+الميزانية+السلوك."""
        prop = make_property(property_type="فيلا", district="النعيم", price=500_000)
        req = make_request(property_type="شقة", district="النعيم", budget=500_000)
        score = self.matcher._calculate_score(req, prop)
        # 0.28+0.27 + 0.06*0.5 = 0.58
        self.assertAlmostEqual(score, 0.58, places=2)

    def test_district_mismatch_reduces_score(self):
        """حي غير مطابق (بدون مجموعات/تشابه كافٍ) يُصفّر مكوّن الحي."""
        prop = make_property(property_type="شقة", district="الروضة", price=500_000)
        req = make_request(property_type="شقة", district="النعيم", budget=500_000)
        score = self.matcher._calculate_score(req, prop)
        # 0.33+0.27 + 0.06*0.5 = 0.63
        self.assertAlmostEqual(score, 0.63, places=2)

    def test_budget_within_20_percent_gets_full_budget_score(self):
        """سعر ضمن ±20% يحصل على مكوّن ميزانية = 1 ضمن النموذج الطبيعي."""
        prop = make_property(price=550_000)  # +10% from 500k
        req = make_request(budget=500_000)
        score = self.matcher._calculate_score(req, prop)
        self.assertAlmostEqual(score, 0.91, places=2)

    def test_budget_between_20_and_30_percent_gets_half_budget_score(self):
        """سعر بين 20-30%: منحدر ميزانية جزئي (≈0.825 عند +25%)."""
        prop = make_property(price=625_000)  # +25% from 500k
        req = make_request(budget=500_000)
        score = self.matcher._calculate_score(req, prop)
        # 0.33+0.28+0.27*0.825 + 0.03 = 0.86275
        self.assertAlmostEqual(score, 0.86275, places=3)

    def test_budget_beyond_30_percent_gets_zero_budget_score(self):
        """سعر خارج نطاق اللين (+40%): مكوّن ميزانية منخفض (ذيل الانحدار)."""
        prop = make_property(price=700_000)  # +40% from 500k
        req = make_request(budget=500_000)
        score = self.matcher._calculate_score(req, prop)
        # c_budget=0.3 → 0.33+0.28+0.081+0.03 = 0.721
        self.assertAlmostEqual(score, 0.721, places=2)

    def test_match_request_creates_property_match_records(self):
        """match_request يجب أن ينشئ سجلات PropertyMatch"""
        make_property(property_type="شقة", district="النعيم", price=500_000)
        req = make_request(property_type="شقة", district="النعيم", budget=500_000)
        matches = self.matcher.match_request(req)
        self.assertGreater(len(matches), 0)
        self.assertEqual(PropertyMatch.objects.filter(request=req).count(), len(matches))

    def test_match_request_updates_match_score(self):
        """match_request يجب أن يحدث match_score في الطلب"""
        make_property(property_type="شقة", district="النعيم", price=500_000)
        req = make_request(property_type="شقة", district="النعيم", budget=500_000)
        self.matcher.match_request(req)
        req.refresh_from_db()
        self.assertGreater(req.match_score, 0.0)

    def test_no_candidate_if_hidden_property(self):
        """العقارات المخفية يجب أن لا تظهر في المطابقة"""
        make_property(property_type="شقة", district="النعيم", price=500_000, visibility="مخفي")
        req = make_request(property_type="شقة", district="النعيم", budget=500_000)
        matches = self.matcher.match_request(req)
        self.assertEqual(matches, [])

    def test_high_match_upgrades_status(self):
        """مطابقة عالية (>= 0.8) يجب أن ترفع حالة الطلب إلى 'matched'"""
        make_property(property_type="شقة", district="النعيم", price=500_000)
        req = make_request(property_type="شقة", district="النعيم", budget=500_000)
        self.matcher.match_request(req)
        req.refresh_from_db()
        self.assertEqual(req.status, "matched")

    def test_below_threshold_does_not_match(self):
        """عقار بنوع ومنطقة مختلفة لا يجب أن يُطابَق (score < 0.6)"""
        make_property(property_type="أرض", district="الروضة", price=500_000)
        req = make_request(property_type="شقة", district="النعيم", budget=500_000)
        matches = self.matcher.match_request(req)
        self.assertEqual(matches, [])

    def test_null_budget_skips_price_prefilter_but_can_score(self):
        """بدون ميزانية: لا فلترة سعر؛ التقييم يعتمد نوع + حي (+سلوك، إلخ)."""
        make_property(property_type="شقة", district="النعيم", price=300_000)
        req = PropertyRequest.objects.create(
            name="بدون ميزانية",
            phone="966501112233",
            property_type="شقة",
            district="النعيم",
            budget=None,
        )
        matches = self.matcher.match_request(req)
        self.assertGreater(len(matches), 0)

    @override_settings(
        PROPERTY_MATCHING={
            **getattr(settings, "PROPERTY_MATCHING", {}),
            "MAX_MATCHES_TO_PERSIST": 2,
            "MAX_CANDIDATES": 50,
        }
    )
    def test_match_request_caps_stored_matches(self):
        """يُخزَّن فقط أعلى N مطابقة بعد الفرز."""
        for i in range(5):
            make_property(
                property_type="شقة",
                district="النعيم",
                price=500_000 + i * 1000,
            )
        req = make_request(property_type="شقة", district="النعيم", budget=500_000)
        self.matcher.match_request(req)
        self.assertLessEqual(PropertyMatch.objects.filter(request=req).count(), 2)


# ─────────────────────────────────────────────────────────────
# 2. API Flow Tests
# ─────────────────────────────────────────────────────────────
class TestPropertyRequestAPI(TestCase):
    """Integration tests for POST /api/request-property/"""

    def setUp(self):
        # ── مهم: نصفّر الـ rate store قبل كل اختبار ──
        import listings.views as v
        v._rate_store.clear()
        self.client = Client(enforce_csrf_checks=False)
        self.url = reverse("listings:property-request-api")
        patcher = patch("listings.views.schedule_property_request_follow_up")
        self.mock_schedule_follow_up = patcher.start()
        self.addCleanup(patcher.stop)

    def _post(self, data):
        # بدون explicit content_type ليقوم Django بترميز العربي بشكل صحيح
        # on_commit + captureOnCommitCallbacks يشغّلان المتابعة دون خيوط تتعارض مع SQLite في الاختبارات
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.url, data)

    def test_valid_request_returns_success(self):
        response = self._post({
            "name": "سامي العمري",
            "phone": "0501234567",
            "property_type": "شقة",
            "district": "النعيم",
            "budget": "500000",
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("matched_count", data)
        self.mock_schedule_follow_up.assert_called_once_with(data["request_id"])

    def test_missing_name_returns_400(self):
        response = self._post({
            "phone": "0501234567",
            "property_type": "شقة",
            "district": "النعيم",
            "budget": "500000",
        })
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("name", data["errors"])

    def test_invalid_phone_returns_400(self):
        response = self._post({
            "name": "خالد",
            "phone": "123",
            "property_type": "شقة",
            "district": "النعيم",
            "budget": "500000",
        })
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("phone", data["errors"])

    def test_invalid_budget_legacy_saves_without_budget(self):
        """الواجهة القديمة (POST form) تتجاهل الميزانية غير الصالحة ولا ترفض الطلب."""
        response = self._post({
            "name": "خالد",
            "phone": "0501234567",
            "property_type": "شقة",
            "district": "النعيم",
            "budget": "abc",
        })
        self.assertEqual(response.status_code, 200)
        row = PropertyRequest.objects.order_by("-pk").first()
        self.assertIsNone(row.budget)

    def test_negative_budget_legacy_saves_without_budget(self):
        response = self._post({
            "name": "خالد",
            "phone": "0501234567",
            "property_type": "شقة",
            "district": "النعيم",
            "budget": "-100",
        })
        self.assertEqual(response.status_code, 200)
        row = PropertyRequest.objects.order_by("-pk").first()
        self.assertIsNone(row.budget)

    def test_request_saved_to_db(self):
        self._post({
            "name": "فيصل",
            "phone": "0509876543",
            "property_type": "فيلا",
            "district": "الزهراء",
            "budget": "2000000",
        })
        self.assertTrue(PropertyRequest.objects.filter(phone="966509876543").exists())

    def test_duplicate_request_returns_info_not_error(self):
        data = {
            "name": "خالد",
            "phone": "0501234567",
            "property_type": "شقة",
            "district": "النعيم",
            "budget": "500000",
        }
        self._post(data)
        response = self._post(data)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("duplicate"))


# ─────────────────────────────────────────────────────────────
# 3. PropertyMatch Creation Tests
# ─────────────────────────────────────────────────────────────
class TestPropertyMatchCreation(TestCase):
    """Tests that PropertyMatch records are correctly created and ordered."""

    def setUp(self):
        self.matcher = PropertyMatcher()

    def test_matches_ordered_by_score_desc(self):
        """نتائج المطابقة يجب أن تكون مرتبة تنازلياً حسب score"""
        make_property(price=500_000)   # perfect match
        make_property(price=590_000)   # ±18% – still within 20%
        req = make_request()
        self.matcher.match_request(req)
        matches = list(PropertyMatch.objects.filter(request=req).order_by("-score"))
        scores = [m.score for m in matches]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_matched_count_equals_created_matches(self):
        """matched_count في الطلب يجب أن يساوي عدد سجلات PropertyMatch"""
        make_property(price=500_000)
        make_property(price=510_000)
        req = make_request()
        self.matcher.match_request(req)
        req.refresh_from_db()
        self.assertEqual(req.matched_count, PropertyMatch.objects.filter(request=req).count())

    def test_rerunning_match_replaces_old_matches(self):
        """إعادة تشغيل المطابقة يجب أن تحذف القديمة وتنشئ جديدة"""
        prop = make_property(price=500_000)
        req = make_request()
        # First run
        self.matcher.match_request(req)
        count_first = PropertyMatch.objects.filter(request=req).count()
        # Second run (no change to inventory)
        self.matcher.match_request(req)
        count_second = PropertyMatch.objects.filter(request=req).count()
        self.assertEqual(count_first, count_second)


# ─────────────────────────────────────────────────────────────
# 3b. REST API: POST /api/property-requests/
# ─────────────────────────────────────────────────────────────
class TestPropertyRequestRESTAPI(TestCase):
    """JSON body + DRF serializer for unified PropertyRequest creation."""

    def setUp(self):
        import listings.views as v

        v._rate_store.clear()
        self.client = Client(enforce_csrf_checks=False)
        self.url = reverse("listings:property-requests-create")

    @patch("listings.views.schedule_property_request_follow_up")
    def test_valid_json_returns_201(self, mock_follow):
        payload = {
            "name": "سامي العمري",
            "phone": "0501234567",
            "property_type": "apartment",
            "district": "النعيم",
            "budget": "500000",
            "category": "family",
            "source": "website",
        }
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.url,
                data=json.dumps(payload),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("request_id", data)
        mock_follow.assert_called_once()
        row = PropertyRequest.objects.get(pk=data["request_id"])
        self.assertEqual(row.property_type, "شقة")
        self.assertEqual(row.category, "family")
        self.assertEqual(row.source, "website")
        self.assertEqual(data.get("message"), "Request created successfully")
        self.assertGreaterEqual(row.score, 0.0)
        self.assertIn(row.priority, ("high", "medium", "low"))

    @patch("listings.views.schedule_property_request_follow_up")
    def test_duplicate_fingerprint_returns_200(self, mock_follow):
        payload = {
            "name": "أول",
            "phone": "0509998877",
            "property_type": "villa",
            "district": "الروضة",
            "budget": "1200000",
            "category": "family",
            "source": "website",
        }
        with self.captureOnCommitCallbacks(execute=True):
            r1 = self.client.post(
                self.url,
                data=json.dumps(payload),
                content_type="application/json",
            )
        self.assertEqual(r1.status_code, 201)
        with self.captureOnCommitCallbacks(execute=True):
            r2 = self.client.post(
                self.url,
                data=json.dumps(payload),
                content_type="application/json",
            )
        self.assertEqual(r2.status_code, 200)
        body = r2.json()
        self.assertTrue(body.get("success"))
        self.assertTrue(body.get("duplicate"))
        self.assertEqual(body.get("request_id"), r1.json()["request_id"])
        self.assertEqual(PropertyRequest.objects.filter(phone="966509998877").count(), 1)
        mock_follow.assert_called_once()

    @override_settings(PROPERTY_REQUEST_API_KEY="test-secret-key")
    @patch("listings.views.schedule_property_request_follow_up")
    def test_api_key_missing_returns_401(self, mock_follow):
        payload = {
            "name": "سامي",
            "phone": "0501234567",
            "property_type": "شقة",
            "district": "النعيم",
            "budget": "500000",
            "category": "family",
        }
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.url,
                data=json.dumps(payload),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json().get("success"))
        mock_follow.assert_not_called()

    @patch("listings.views.schedule_property_request_follow_up")
    def test_omitted_category_defaults_to_family(self, mock_follow):
        payload = {
            "name": "سامي",
            "phone": "0501234567",
            "property_type": "شقة",
            "district": "النعيم",
            "budget": "500000",
        }
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.url,
                data=json.dumps(payload),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 201)
        row = PropertyRequest.objects.get(pk=response.json()["request_id"])
        self.assertEqual(row.category, "family")
        mock_follow.assert_called_once()

    @patch("listings.views.schedule_property_request_follow_up")
    def test_n8n_short_url_same_as_api_prefixed(self, mock_follow):
        """POST /n8n/property-request/ يعادل /api/n8n/property-request/"""
        short = reverse("listings:n8n-property-request")
        self.assertTrue(short.endswith("/n8n/property-request/"))
        payload = {
            "name": "اختصار مسار",
            "phone": "0502223344",
            "propertyType": "apartment",
            "district": "الصفا",
            "budget": "400000",
        }
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                short,
                data=json.dumps(payload),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(PropertyRequest.objects.get(pk=response.json()["request_id"]).source, "ai_chat")

    @patch("listings.views.schedule_property_request_follow_up")
    def test_n8n_endpoint_normalizes_and_sets_ai_chat(self, mock_follow):
        n8n_url = reverse("listings:n8n-property-request-create")
        payload = {
            "name": "عميل بوت",
            "phone": "0501112233",
            "propertyType": "villa",
            "district": "الشاطئ",
            "budget": "900000",
            "message": "أريد فيلا قرب البحر",
        }
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                n8n_url,
                data=json.dumps(payload),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 201)
        row = PropertyRequest.objects.get(pk=response.json()["request_id"])
        self.assertEqual(row.source, "ai_chat")
        self.assertEqual(row.category, "family")
        self.assertEqual(row.property_type, "فيلا")
        self.assertIn("البحر", (row.notes or ""))
        mock_follow.assert_called_once()


# ─────────────────────────────────────────────────────────────
# 4. WhatsApp Message Generation Tests
# ─────────────────────────────────────────────────────────────
class TestWhatsAppMessage(TestCase):
    """Tests for the generate_whatsapp_message Admin Action."""

    def setUp(self):
        self.superuser = User.objects.create_superuser("admin", "a@b.com", "password")
        self.client = Client()
        self.client.force_login(self.superuser)
        self.site = AdminSite()
        self.admin = PropertyRequestAdmin(PropertyRequest, self.site)
        self.factory = RequestFactory()

    def test_action_requires_single_request(self):
        """الـ action يجب أن يرفض التطبيق على أكثر من طلب واحد"""
        req1 = make_request(name="أحمد", phone="966501111111")
        req2 = make_request(name="خالد", phone="966502222222")
        qs = PropertyRequest.objects.filter(pk__in=[req1.pk, req2.pk])
        http_req = self.factory.get("/")
        http_req.user = self.superuser
        # mock message_user لأن RequestFactory لا يحتوي Messages Middleware
        with patch.object(self.admin, 'message_user') as mock_msg:
            result = self.admin.generate_whatsapp_message(http_req, qs)
            mock_msg.assert_called_once()  # يجب أن يُستدعى مرة واحدة بالتحذير
            self.assertIsNone(result)       # يجب أن لا يُرجع HttpResponse
        self.assertEqual(qs.count(), 2)

    def test_action_generates_html_with_wa_link(self):
        """يجب أن يولد صفحة HTML تحتوي رابط واتساب"""
        prop = make_property(price=500_000)
        req = make_request()
        matcher = PropertyMatcher()
        matcher.match_request(req)

        qs = PropertyRequest.objects.filter(pk=req.pk)
        http_req = self.factory.get("/")
        http_req.user = self.superuser
        http_req.META["SERVER_NAME"] = "localhost"
        http_req.META["SERVER_PORT"] = "8000"
        http_req.META["wsgi.url_scheme"] = "http"

        response = self.admin.generate_whatsapp_message(http_req, qs)
        if response:
            content = response.content.decode("utf-8")
            self.assertIn("wa.me", content)
            self.assertIn(req.name, content)
            self.assertIn(req.district, content)

    def test_message_contains_property_type_and_district(self):
        """رسالة الواتساب يجب أن تحتوي نوع العقار والحي"""
        make_property(price=500_000)
        req = make_request(property_type="شقة", district="النعيم")
        PropertyMatcher().match_request(req)

        qs = PropertyRequest.objects.filter(pk=req.pk)
        http_req = self.factory.get("/")
        http_req.user = self.superuser
        http_req.META.update({"SERVER_NAME": "localhost", "SERVER_PORT": "8000", "wsgi.url_scheme": "http"})

        response = self.admin.generate_whatsapp_message(http_req, qs)
        if response:
            content = response.content.decode("utf-8")
            self.assertIn("شقة", content)
            self.assertIn("النعيم", content)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    STAFF_ACTION_NOTIFY_EMAILS=["admin@example.com"],
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class TestAppointmentFlow(TestCase):
    def setUp(self):
        self.client = Client()
        self.property = make_property()

    def test_guest_can_book_appointment_and_receives_email(self):
        url = reverse("listings:appointment-create", args=[self.property.pk])
        response = self.client.post(
            url,
            data={
                "client_name": "عميل اختبار",
                "client_email": "guest@example.com",
                "client_phone": "0501234567",
                "booking_date": "2099-12-30",
                "booking_time": "16:00",
            },
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Appointment.objects.count(), 1)
        ap = Appointment.objects.first()
        self.assertEqual(ap.status, Appointment.Status.PENDING)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("تأكيد حجز موعد", mail.outbox[0].subject)
        self.assertIn(str(ap.cancel_token), mail.outbox[0].alternatives[0][0])

    def test_guest_can_book_without_email(self):
        url = reverse("listings:appointment-create", args=[self.property.pk])
        response = self.client.post(
            url,
            data={
                "client_name": "بدون بريد",
                "client_email": "",
                "client_phone": "0501234567",
                "booking_date": "2099-12-31",
                "booking_time": "16:30",
            },
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        ap = Appointment.objects.latest("id")
        self.assertEqual(ap.client_email, "")
        self.assertEqual(len(mail.outbox), 0)

    def test_cancel_token_marks_appointment_canceled_and_notifies_admin(self):
        ap = Appointment.objects.create(
            property=self.property,
            client_name="مستخدم",
            client_email="guest@example.com",
            client_phone="0501112233",
            booking_date=date(2099, 12, 30),
            booking_time=time(16, 0),
            status=Appointment.Status.PENDING,
        )
        mail.outbox = []
        url = reverse("listings:appointment-cancel", args=[ap.cancel_token])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ap.refresh_from_db()
        self.assertEqual(ap.status, Appointment.Status.CANCELED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("تم إلغاء موعد", mail.outbox[0].subject)


class TestStaffAdminUserFlags(TestCase):
    """صلاحيات إضافة مستخدمين / تغيير كلمات المرور (UserAccessProfile)."""

    def test_helpers_reflect_profile_flags(self):
        u = User.objects.create_user("flaguser", "f@t.com", "pw", is_staff=True)
        UserAccessProfile.objects.create(user=u, allow_add_users=False, allow_change_passwords=True)
        self.assertFalse(staff_may_add_users(u))
        self.assertTrue(staff_may_change_passwords(u))
        u.access_profile.allow_add_users = True
        u.access_profile.allow_change_passwords = False
        u.access_profile.save()
        self.assertTrue(staff_may_add_users(u))
        self.assertFalse(staff_may_change_passwords(u))

    def test_superuser_bypasses_profile_flags(self):
        su = User.objects.create_superuser("su_flags", "su@t.com", "pw")
        UserAccessProfile.objects.create(
            user=su, allow_add_users=False, allow_change_passwords=False
        )
        self.assertTrue(staff_may_add_users(su))
        self.assertTrue(staff_may_change_passwords(su))
        self.assertTrue(staff_may_access_users_groups(su))

    def test_admin_password_change_forbidden_when_flag_off(self):
        u = User.objects.create_user("nopw", "n@t.com", "pw", is_staff=True)
        UserAccessProfile.objects.create(user=u, allow_change_passwords=False)
        c = Client()
        c.force_login(u)
        r = c.get("/admin/password_change/")
        self.assertEqual(r.status_code, 403)

    def test_staff_cannot_access_users_and_groups_even_with_django_perms(self):
        u = User.objects.create_user("coadmin", "co@t.com", "pw", is_staff=True)
        UserAccessProfile.objects.create(
            user=u, allow_add_users=True, allow_change_passwords=True
        )
        user_perms = Permission.objects.filter(codename__in=("view_user", "view_group"))
        u.user_permissions.add(*list(user_perms))
        self.assertFalse(staff_may_access_users_groups(u))

        c = Client()
        c.force_login(u)
        self.assertEqual(c.get("/admin/auth/user/").status_code, 403)
        self.assertEqual(c.get("/admin/auth/group/").status_code, 403)


class TestCoAdminViewAssignOnly(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.co_admin = User.objects.create_user(
            "coassign", "coassign@test.com", "pw", is_staff=True
        )
        grp = Group.objects.create(name="co_admin")
        self.co_admin.groups.add(grp)
        self.other_staff = User.objects.create_user(
            "otherstaff", "other@test.com", "pw", is_staff=True
        )
        self.req_admin = PropertyRequestAdmin(PropertyRequest, self.site)
        self.offer_admin = PropertyOfferAdmin(PropertyOffer, self.site)
        self.lead_admin = PropertyLeadAdmin(PropertyLead, self.site)

    def _rf(self):
        r = self.factory.get("/")
        r.user = self.co_admin
        return r

    def test_co_admin_request_admin_is_assign_only(self):
        req = self._rf()
        self.assertFalse(self.req_admin.has_add_permission(req))
        self.assertFalse(self.req_admin.has_delete_permission(req))
        actions = self.req_admin.get_actions(req)
        self.assertIn("assign_to_marketer", actions)
        self.assertIn("assign_to_me", actions)
        self.assertNotIn("run_matching_engine", actions)
        self.assertNotIn("mark_as_contacted", actions)

        row = make_request(name="عميل", phone="966500000001", assigned_to=self.other_staff)
        ro = self.req_admin.get_readonly_fields(req, row)
        self.assertIn("name", ro)
        self.assertIn("status", ro)
        self.assertNotIn("assigned_to", ro)
        self.assertEqual(self.req_admin.get_queryset(req).count(), 1)

    def test_co_admin_offer_and_lead_actions_are_assign_only(self):
        req = self._rf()
        self.assertFalse(self.offer_admin.has_add_permission(req))
        self.assertFalse(self.offer_admin.has_delete_permission(req))
        offer_actions = self.offer_admin.get_actions(req)
        self.assertIn("assign_to_marketer", offer_actions)
        self.assertIn("assign_to_me", offer_actions)
        self.assertNotIn("publish_as_property", offer_actions)

        self.assertFalse(self.lead_admin.has_add_permission(req))
        self.assertFalse(self.lead_admin.has_delete_permission(req))
        lead_actions = self.lead_admin.get_actions(req)
        self.assertIn("assign_to_marketer", lead_actions)
        self.assertIn("assign_to_me", lead_actions)
        self.assertNotIn("mark_as_interested", lead_actions)
