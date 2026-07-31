/**
 * behavioral_tracker.js
 * نظام تتبع وتقييم سلوك الزوار (Behavioral Scoring & Dynamic UI)
 * ---------------------------------------------------------
 * 1. يتتبع اهتمامات الزائر (نوع العقار، الحي).
 * 2. يمنح نقاطاً بناءً على التفاعل (مشاهدة، مشاركة، تمرير).
 * 3. يغير واجهة المستخدم ديناميكياً (Dynamic UI).
 */

const BehavioralTracker = (() => {
    "use strict";

    const STORAGE_KEY = "jodah_behavior_v1";
    const SCORE_LIMIT_FOR_VIP = 50;

    const initialState = {
        score: 0,
        recentlyViewed: [], // IDs
        interests: {
            types: {},      // { 'فيلا': 5, 'شقة': 2 }
            districts: {}   // { 'الشاطئ': 3 }
        },
        lastAction: Date.now(),
        hasConverted: false // if they already filled a form
    };

    let state = JSON.parse(localStorage.getItem(STORAGE_KEY)) || initialState;

    function save() {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    }

    // ===== نقاط التفاعل =====
    const POINTS = {
        VIEW_PROPERTY: 10,
        CLICK_IMAGE: 5,
        SHARE_LINK: 15,
        SCROLL_DEEP: 5,
        SEARCH: 8
    };

    function addScore(points, reason = "") {
        state.score += points;
        state.lastAction = Date.now();
        console.log(`[Behavioral] +${points} pts (${reason}). Total: ${state.score}`);
        save();
        updateDynamicUI();
    }

    function trackInterest(type, value) {
        if (!value) return;
        if (!state.interests[type]) state.interests[type] = {};
        state.interests[type][value] = (state.interests[type][value] || 0) + 1;
        save();
    }

    function getTopInterest(type) {
        const items = state.interests[type] || {};
        let top = null;
        let max = 0;
        for (const [key, val] of Object.entries(items)) {
            if (val > max) {
                max = val;
                top = key;
            }
        }
        return top;
    }

    // ===== التغيير الديناميكي للواجهة =====
    function updateDynamicUI() {
        // 1. تغيير نص الهيرو بناءً على الاهتمام (تم التعطيل بناءً على طلب المستخدم لتوحيد العنوان)
        /*
        const topType = getTopInterest('types');
        const heroTitle = document.querySelector('.hero-text h1');
        if (heroTitle && topType && state.score > 20) {
            heroTitle.innerText = `أفضل عروض ال${topType} العقارية في جدة`;
        }
        */

        // 2. إظهار قسم "شوهد مؤخراً" إذا كان هناك بيانات
        const recentlySection = document.getElementById('recently-viewed-container');
        if (recentlySection && state.recentlyViewed.length > 0) {
            recentlySection.style.display = 'block';
        }

        // 3. تمييز الأزرار لعملاء الـ VIP (نقاط عالية)
        if (state.score >= SCORE_LIMIT_FOR_VIP) {
            document.querySelectorAll('.btn-action').forEach(btn => {
                btn.classList.add('vip-glow');
            });
        }
    }

    // ===== العقارات المشاهدة مؤخراً =====
    function trackPropertyView(id, type, district) {
        if (!state.recentlyViewed.includes(id)) {
            state.recentlyViewed.unshift(id);
            if (state.recentlyViewed.length > 6) state.recentlyViewed.pop();
        }
        trackInterest('types', type);
        trackInterest('districts', district);
        addScore(POINTS.VIEW_PROPERTY, "Property View");
        save();
    }

    function openWhatsAppConsult() {
        const topType = getTopInterest('types') || "عقارات";
        const topDistrict = getTopInterest('districts') || "جدة";
        const text = `السلام عليكم، كنت أتصفح موقعكم ومهتم بـ ${topType} في ${topDistrict}. هل توجد عروض حصرية حالياً؟`;
        window.location.href = `https://wa.me/966530460992?text=${encodeURIComponent(text)}`;
    }

    // ===== إعداد الفعاليات =====
    function init() {
        updateDynamicUI();

        // تتبع التمرير العميق
        let scrolledDeep = false;
        window.addEventListener('scroll', () => {
            if (!scrolledDeep && window.scrollY > 1500) {
                scrolledDeep = true;
                addScore(POINTS.SCROLL_DEEP, "Deep Scroll");
            }
        }, { passive: true });

        // تتبع النقر على الصور (في صفحة التفاصيل)
        document.addEventListener('click', (e) => {
            if (e.target.closest('.swiper-slide img')) {
                addScore(POINTS.CLICK_IMAGE, "Image Interaction");
            }
        });
    }

    window.BehavioralTracker = {
        init,
        trackPropertyView,
        addScore,
        POINTS,
        state,
        openWhatsAppConsult
    };
})();

// التشغيل
document.addEventListener('DOMContentLoaded', () => {
    if (window.BehavioralTracker && typeof window.BehavioralTracker.init === 'function') {
        window.BehavioralTracker.init();
    }
});
