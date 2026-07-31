/* admin_custom.js – جودة المستقبل Admin enhancements */
console.log("Admin Custom v34: Script initialized");

document.addEventListener('DOMContentLoaded', function () {
    var isMobileViewport = window.innerWidth < 992;
    if (isMobileViewport) {
        document.body.classList.add('jodah-mobile-perf');
    }

    // ── Mobile: Backdrop logic ──
    var backdrop = document.getElementById('admin-sidebar-backdrop');
    if (!backdrop) {
        backdrop = document.createElement('div');
        backdrop.id = 'admin-sidebar-backdrop';
        backdrop.setAttribute('aria-hidden', 'true');
        backdrop.setAttribute('aria-label', 'إغلاق القائمة');
        backdrop.style.cssText = 'display:none;position:fixed;inset:0;background:rgba(7,16,28,0.82);z-index:11990;cursor:pointer;-webkit-tap-highlight-color:transparent;';
        document.body.appendChild(backdrop);
    }

    function isMobile() { return window.innerWidth < 992; }
    
    function updateBackdrop() {
        var isOpen = document.body.classList.contains('sidebar-open');
        var mobile = isMobile();
        if (isOpen && mobile) {
            if (backdrop.style.display !== 'block') backdrop.style.display = 'block';
            if (!document.body.classList.contains('sidebar-backdrop-open')) {
                document.body.classList.add('sidebar-backdrop-open');
            }
        } else {
            if (backdrop.style.display !== 'none') backdrop.style.display = 'none';
            if (document.body.classList.contains('sidebar-backdrop-open')) {
                document.body.classList.remove('sidebar-backdrop-open');
            }
        }
    }

    function closeSidebar() {
        /* AdminLTE 4 / Jazzmin: زر القائمة يستخدم data-lte-toggle="sidebar" */
        var btn =
            document.querySelector('[data-lte-toggle="sidebar"]') ||
            document.querySelector('[data-widget="pushmenu"]') ||
            document.querySelector('.nav-link[data-lte-toggle="sidebar"]');
        if (btn) btn.click();
    }

    backdrop.addEventListener('click', closeSidebar);
    backdrop.addEventListener('touchstart', closeSidebar, { passive: true });

    // ── Global Dash-to-Arabic Replacement ──
    function replaceDashes(root) {
        if (!root) return;
        var elements = root.querySelectorAll ? root.querySelectorAll('option, .select2-selection__rendered, .select2-results__option') : [];
        for (var i = 0; i < elements.length; i++) {
            var el = elements[i];
            if (el.textContent.trim() === '---------') {
                el.textContent = 'اختر';
                if (el.hasAttribute && el.hasAttribute('title')) el.setAttribute('title', 'اختر');
            }
        }
    }

    replaceDashes(document);

    /* مراقبة class على body فقط للـ backdrop — أخف من مراقبة subtree كاملة */
    var bodyClassObserver = new MutationObserver(function () {
        updateBackdrop();
    });
    bodyClassObserver.observe(document.body, {
        attributes: true,
        attributeFilter: ['class'],
    });

    /* dash replacement: مراقبة DOM مكلفة على الجوال؛ نحتفظ بها لسطح المكتب فقط */
    if (!isMobileViewport) {
        var dashObserver = new MutationObserver(function (mutations) {
            mutations.forEach(function (m) {
                if (m.type !== 'childList') return;
                m.addedNodes.forEach(function (node) {
                    if (node.nodeType === 1) replaceDashes(node);
                });
            });
        });
        dashObserver.observe(document.body, { childList: true, subtree: true });
    }

    window.addEventListener('resize', updateBackdrop);
    updateBackdrop();

    // ── Visual Fixes ──
    var brandLink = document.querySelector('.main-sidebar .brand-link');
    if (brandLink) {
        brandLink.style.background = '#0d1b2e';
        var brandText = brandLink.querySelector('.brand-text');
        if (brandText) brandText.style.color = '#c5a059';
    }

    /* على الجوال نتخطى تأخيرات الأنيميشن — تخفف بطء اللمس والتمرير */
    if (window.innerWidth >= 992) {
        document.querySelectorAll('.kpi-card').forEach(function (card, i) {
            setTimeout(function () {
                card.style.opacity = '1';
                card.style.transform = 'translateY(0)';
            }, 100 + i * 80);
        });
    } else {
        document.querySelectorAll('.kpi-card').forEach(function (card) {
            card.style.opacity = '1';
            card.style.transform = 'none';
        });
    }

    // ── شريط «الدخول كمسوّق» (مدير يتصفح كمسوّق آخر) ──
    (function () {
        var meta = document.querySelector('meta[name="impersonation-banner"]');
        if (!meta) return;
        var stopUrl = meta.getAttribute('data-stop-url');
        if (!stopUrl) return;
        function getCookie(name) {
            var m = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
            return m ? decodeURIComponent(m[2]) : '';
        }
        var acting = meta.getAttribute('data-acting-as') || meta.getAttribute('data-acting-username') || '';
        var manager = meta.getAttribute('data-manager') || '';
        function esc(s) {
            if (!s) return '';
            var d = document.createElement('div');
            d.textContent = s;
            return d.innerHTML;
        }
        var bar = document.createElement('div');
        bar.id = 'jodah-impersonation-bar';
        bar.setAttribute('dir', 'rtl');
        bar.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:10050;background:linear-gradient(90deg,#1e3a5f,#0f172a);color:#fef3c7;border-bottom:2px solid #c5a059;padding:10px 16px;font-size:0.92rem;display:flex;align-items:center;justify-content:center;gap:14px;flex-wrap:wrap;box-shadow:0 4px 24px rgba(0,0,0,0.35);';
        bar.innerHTML =
            '<span><i class="fas fa-user-secret" style="color:#c5a059;margin-left:8px;"></i>أنت تعمل بحساب المسوّق <strong style="color:#fff;">' +
            esc(acting) +
            '</strong></span>' +
            '<span style="opacity:0.88;font-size:0.85rem;">(مدير النظام: ' +
            esc(manager) +
            ')</span>';
        var form = document.createElement('form');
        form.method = 'post';
        form.action = stopUrl;
        form.style.cssText = 'margin:0;display:inline;';
        var csrf = document.createElement('input');
        csrf.type = 'hidden';
        csrf.name = 'csrfmiddlewaretoken';
        csrf.value = getCookie('csrftoken');
        var btn = document.createElement('button');
        btn.type = 'submit';
        btn.className = 'btn btn-sm';
        btn.style.cssText = 'background:#c5a059;color:#0b1220;border:none;font-weight:700;padding:6px 14px;border-radius:8px;cursor:pointer;';
        btn.textContent = 'العودة لحساب المدير';
        form.appendChild(csrf);
        form.appendChild(btn);
        bar.appendChild(form);
        document.body.insertBefore(bar, document.body.firstChild);
        var pad = document.createElement('style');
        pad.id = 'jodah-impersonation-bar-style';
        pad.textContent =
            'body.impersonation-active { padding-top: 52px !important; } ' +
            '.main-header.navbar-fixed { top: 52px !important; }';
        document.head.appendChild(pad);
        document.body.classList.add('impersonation-active');
    })();

    /* لوحة المسوّق / الإحصائيات: تُعرض عبر Jazzmin custom_links داخل قسم listings — لا حقن JS منفصل */

    /* Jazzmin/AdminLTE: قصّ النص في الشريط قد يفرضه CSS بعد التحميل — نفرض السماح بالتفاف السطور */
    function fixJazzminSidebarLabels() {
        var root = document.getElementById('jazzy-sidebar') || document.querySelector('.main-sidebar');
        if (!root) return;
        /* الجوال: نتجنب المرور على عشرات العناصر inline style لأنه يسبب jank وتأخير تمرير */
        if (window.innerWidth < 992) {
            root.style.removeProperty('width');
            root.style.removeProperty('min-width');
            root.style.removeProperty('max-width');
            root.style.removeProperty('flex');
            return;
        }
        var w = Math.min(window.innerWidth - 12, 272);
        root.style.setProperty('width', w + 'px', 'important');
        root.style.setProperty('min-width', '240px', 'important');
        root.style.setProperty('max-width', w + 'px', 'important');
        root.style.setProperty('background-color', '#07101c', 'important');
        root.querySelectorAll('.nav-link p').forEach(function (p) {
            p.style.removeProperty('min-width');
            p.style.setProperty('white-space', 'normal', 'important');
            p.style.setProperty('overflow', 'visible', 'important');
            p.style.setProperty('text-overflow', 'clip', 'important');
            p.style.setProperty('max-width', 'none', 'important');
        });
        root.querySelectorAll('.nav-header').forEach(function (el) {
            el.style.setProperty('white-space', 'normal', 'important');
            el.style.setProperty('overflow', 'visible', 'important');
            el.style.setProperty('text-overflow', 'clip', 'important');
            el.style.setProperty('max-width', 'none', 'important');
        });
    }
    if (!isMobileViewport) {
        fixJazzminSidebarLabels();
        requestAnimationFrame(function () {
            requestAnimationFrame(fixJazzminSidebarLabels);
        });
    }

    /* موظف غير مدير: إبقاء الشريط ظاهراً على الشاشات الواسعة بعد التنقل بين الصفحات */
    function jodahStaffSidebarStable() {
        if (document.body.getAttribute('data-jodah-staff-sidebar') !== '1') return;
        if (window.matchMedia('(min-width: 992px)').matches) {
            document.body.classList.remove('sidebar-collapse');
            document.body.classList.add('sidebar-open');
        }
    }
    if (!isMobileViewport) {
        jodahStaffSidebarStable();
        requestAnimationFrame(function () {
            jodahStaffSidebarStable();
        });
        window.addEventListener('load', function () {
            setTimeout(jodahStaffSidebarStable, 100);
            setTimeout(jodahStaffSidebarStable, 400);
            setTimeout(jodahStaffSidebarStable, 900);
        });
    }
    /* يغلب تهيئة AdminLTE/Jazzmin المتأخرة؛ يتوقف بعد ~2.5ث حتى لا نلغي طيّ المستخدم يدوياً */
    if (!isMobileViewport && document.body.getAttribute('data-jodah-staff-sidebar') === '1') {
        var _sbUntil = Date.now() + 2500;
        var _sbObs = new MutationObserver(function () {
            if (Date.now() > _sbUntil) {
                _sbObs.disconnect();
                return;
            }
            jodahStaffSidebarStable();
        });
        _sbObs.observe(document.body, { attributes: true, attributeFilter: ['class'] });
    }
    if (!isMobileViewport) {
        var resizeT = null;
        window.addEventListener('resize', function () {
            if (resizeT) clearTimeout(resizeT);
            resizeT = setTimeout(fixJazzminSidebarLabels, 200);
        });
    }
});
