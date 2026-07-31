from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import SESSION_KEY


class ApiJsonErrorMiddleware(MiddlewareMixin):
    """
    لأي مسار يبدأ بـ /api/:
    إذا رجع HTML بسبب 400/403/404/500 نحوله إلى JSON موحّد
    """

    def process_response(self, request, response):
        if request.path.startswith("/api/"):
            ct = response.get("Content-Type", "")
            if "text/html" in ct and response.status_code in (400, 403, 404, 500):
                return JsonResponse(
                    {
                        "ok": False,
                        "message": "",
                        "data": {},
                        "error": f"API returned HTML (status {response.status_code})",
                        "errors": {},
                    },
                    status=response.status_code,
                )
        return response


class ApiCsrfJsonMiddleware(CsrfViewMiddleware):
    """
    لأي مسار يبدأ بـ /api/:
    إذا فشل CSRF لا ترجع صفحة HTML، رجّع JSON
    """

    def _reject(self, request, reason):
        if request.path.startswith("/api/"):
            return JsonResponse(
                {
                    "ok": False,
                    "message": "",
                    "data": {},
                    "error": "CSRF failed",
                    "errors": {"csrf": [str(reason)]},
                },
                status=403,
            )
        return super()._reject(request, reason)


class ImpersonationMiddleware(MiddlewareMixin):
    """
    يسمح للمدير (superuser) بالعمل كمسوّق آخر دون تسجيل خروج:
    الجلسة تبقى للمدير، ويُستبدل request.user بالمسوّق المختار.
    request.impersonator = المدير الحقيقي عند التبديل، وإلا None.
    """

    def process_request(self, request):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        request.impersonator = None

        imp_uid = request.session.get("impersonate_user_id")
        imp_tr = request.session.get("_impersonator_id")
        auth_uid = request.session.get(SESSION_KEY)

        if not imp_uid or not imp_tr or not auth_uid:
            return None

        if str(imp_tr) != str(auth_uid):
            request.session.pop("impersonate_user_id", None)
            request.session.pop("_impersonator_id", None)
            return None

        try:
            impersonator = User.objects.get(pk=imp_tr)
            impersonated = User.objects.get(pk=int(imp_uid), is_active=True)
        except (User.DoesNotExist, ValueError, TypeError):
            request.session.pop("impersonate_user_id", None)
            request.session.pop("_impersonator_id", None)
            return None

        if not impersonator.is_superuser:
            request.session.pop("impersonate_user_id", None)
            request.session.pop("_impersonator_id", None)
            return None

        request.impersonator = impersonator
        request.user = impersonated
        return None


class DateAccessMiddleware(MiddlewareMixin):
    """
    ميدل وير للتحقق من تاريخ صلاحية دخول المستخدم.
    إذا كان المستخدم مسجلاً للدخول ولديه ملف صلاحية (UserAccessProfile)، 
    يتم التحقق من تاريخ البداية والنهاية. إذا كان خارج الفترة، يتم تسجيل خروجه وتوجيهه لرسالة خطأ.
    """
    def process_request(self, request):
        if not request.user.is_authenticated:
            return None

        # أثناء «التبديل كمسوّق» لا نطبّق قيود تاريخ الدخول على الحساب المستعار (تجنّب تسجيل خروج المدير)
        if getattr(request, "impersonator", None) is not None:
            return None

        # استثناء مدراء النظام الخارقين (Superusers) من هذا الفحص إذا أردت
        # if request.user.is_superuser:
        #     return None

        try:
            from listings.models import UserAccessProfile
            from django.utils import timezone
            from django.contrib.auth import logout
            from django.contrib import messages
            from django.shortcuts import redirect

            profile = request.user.access_profile
            today = timezone.localtime().date()

            if profile.access_start_date and today < profile.access_start_date:
                logout(request)
                messages.error(request, f"حسابك غير مفعل بعد. يبدأ التفعيل في: {profile.access_start_date}")
                return redirect('admin:login')

            if profile.access_end_date and today > profile.access_end_date:
                logout(request)
                messages.error(request, f"انتهت فترة صلاحية حسابك في: {profile.access_end_date}")
                return redirect('admin:login')

        except Exception:
            # إذا لم يكن لديه UserAccessProfile (مثل المستخدمين القدامى)، يتم السماح له بالدخول
            pass

        return None

class MarketerTrackingMiddleware(MiddlewareMixin):
    """
    ميدل وير لالتقاط معرف المسوق من الرابط (?m=ID) 
    وتخزينه في الجلسة (session) لتتبع الزيارات والطلبات لاحقاً.
    """
    def process_request(self, request):
        marketer_id = request.GET.get('m')
        if marketer_id:
            # تخزين معرف المسوق في الجلسة لمدة طويلة (مثلاً 30 يوم)
            request.session['marketer_id'] = marketer_id
        return None


class StaffAdminPasswordGateMiddleware(MiddlewareMixin):
    """
    يمنع موظفاً عُطّلت له صلاحية «تغيير كلمات المرور» من الوصول إلى
    /admin/password_change/ (تغيير كلمة مرور الحساب الحالي في الأدمن).
    """

    def process_view(self, request, view_func, view_args, view_kwargs):
        path = request.path or ""
        if not path.startswith("/admin/password_change"):
            return None
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return None
        from listings.utils.staff_permissions import admin_actor, staff_may_change_passwords

        actor = admin_actor(request)
        if not getattr(actor, "is_staff", False):
            return None
        if not staff_may_change_passwords(actor):
            raise PermissionDenied(
                "غير مسموح لك بتغيير كلمة المرور من لوحة الإدارة. تواصل مع مدير النظام."
            )
        return None


class MarketerAdminHomeRedirectMiddleware(MiddlewareMixin):
    """
    موظف (staff) غير superuser: الصفحة الرئيسية للأدمن /admin/ → لوحة «إحصائياتي».
    يمنع وميض إعادة التوجيه من القالب ويُبقي تجربة الشريط الجانبي متسقة.
    """

    def process_request(self, request):
        if request.method != "GET":
            return None
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None
        if not user.is_staff or user.is_superuser:
            return None
        from listings.utils.staff_permissions import staff_is_co_admin
        if staff_is_co_admin(user):
            return None
        p = request.path.rstrip("/") or "/"
        if p != "/admin":
            return None
        from django.shortcuts import redirect
        from django.urls import reverse

        return redirect(reverse("listings:marketer-dashboard"))
