/* main.js (fixed + stable)
   ✅ يمنع أخطاء DOM (form not found / removeChild)
   ✅ يمنع تكرار event listeners
   ✅ Pagination ثابت بدون MutationObserver (السبب الرئيسي للتعليق)
   ✅ روابط request-property تكون relative (بدون 127.0.0.1)
   ✅ طلب عقار: POST إلى /api/request-property/ بـ FormData + CSRF
   ✅ lead + عرض عقار: إلى CRM (window.APPS_SCRIPT_URL) + واتساب
   ✅ القائمة المنسدلة الاحترافية للموبايل (Smooth Animation + Overlay)
*/

(() => {
    "use strict";

    // ===== Helpers =====
    function toAsciiDigits(input) {
        return String(input || "").replace(/[٠-٩۰-۹]/g, (d) => {
            const code = d.charCodeAt(0);
            // Arabic-Indic ٠-٩
            if (code >= 0x0660 && code <= 0x0669) return String(code - 0x0660);
            // Extended Arabic-Indic ۰-۹
            if (code >= 0x06f0 && code <= 0x06f9) return String(code - 0x06f0);
            return d;
        });
    }

    function normalizeSaudiPhone(input) {
        let phone = toAsciiDigits(input).replace(/[^\d]/g, "");
        if (!phone) return "";
        if (phone.startsWith("00")) phone = phone.slice(2);
        if (phone.startsWith("05") && phone.length === 10) phone = "9665" + phone.slice(2);
        else if (phone.length === 9 && phone.startsWith("5")) phone = "966" + phone;
        else if (phone.startsWith("96605") && phone.length === 13) phone = "966" + phone.slice(4);
        return phone;
    }

    function isValidSaudiMobile(input) {
        const phone = normalizeSaudiPhone(input);
        return /^9665\d{8}$/.test(phone);
    }

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== "") {
            const cookies = document.cookie.split(";");
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === name + "=") {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        // Fallback for CSRF_USE_SESSIONS: check the DOM for the token
        if (!cookieValue && name === "csrftoken") {
            const tokenInput = document.querySelector("[name=csrfmiddlewaretoken]");
            if (tokenInput) cookieValue = tokenInput.value;
        }
        return cookieValue;
    }

    function isSafeHttpUrl(url) {
        try {
            const u = new URL(String(url));
            return u.protocol === "https:" || u.protocol === "http:";
        } catch {
            return false;
        }
    }

    function WHATSAPP_NUMBER() {
        return "966530460992";
    }

    function safeRemoveById(id) {
        const el = document.getElementById(id);
        if (el && el.parentNode) el.parentNode.removeChild(el);
    }

    function setBtnLoading(btn, loadingHtml) {
        if (!btn) return { restore: () => { } };
        const original = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = loadingHtml;
        return {
            restore: () => {
                btn.disabled = false;
                btn.innerHTML = original;
            },
        };
    }

    // ===== Global Success Modal =====
    function showSuccessModal(configOrTitle, message, whatsappUrl) {
        let config = {};
        if (typeof configOrTitle === "object" && configOrTitle !== null) {
            config = configOrTitle;
        } else {
            config = { title: configOrTitle, message, whatsappUrl };
        }

        const {
            title = "تم استلام استفسارك بنجاح",
            message: msg = "فريق الركن الأوسط سيقوم بالرد عليك في أقرب وقت ممكن.",
            name = "",
            subject = "",
            waCustomMsg = "",
            whatsappUrl: waUrl = "",
        } = config;

        const modal = document.getElementById("global-success-modal");
        const waBtn = document.getElementById("modal-whatsapp-btn");
        const titleEl = document.getElementById("modal-title");
        const msgEl = document.getElementById("modal-message");

        if (modal && waBtn) {
            if (titleEl) titleEl.innerText = title;
            if (msgEl) {
                msgEl.innerHTML = `${msg}<br><small style="display:block; margin-top:10px; color:#64748b; font-size:0.9rem;">يمكنك التواصل معنا مباشرة عبر واتساب للحصول على رد أسرع</small>`;
            }

            if (waUrl || waUrl) {
                waBtn.href = waUrl || waUrl;
                waBtn.parentElement.style.display = "flex";
            } else {
                const waPhone = WHATSAPP_NUMBER();
                const waText = waCustomMsg || `السلام عليكم معك ${name} وموضوعي بخصوص ${subject}`;
                waBtn.href = `https://wa.me/${waPhone}?text=${encodeURIComponent(waText)}`;
                waBtn.parentElement.style.display = "flex";
            }

            modal.style.display = "flex";
            setTimeout(() => modal.classList.add("active"), 10);
        } else {
            alert(title + "\n" + msg);
        }
    }

    window.showSuccessModal = showSuccessModal;

    // ===== CRM Submit (lead + owner_offer) =====
    async function submitToCRM(formData, type) {
        const apiURL = window.APPS_SCRIPT_URL;
        if (!apiURL) throw new Error("APPS_SCRIPT_URL غير موجود");
        if (!isSafeHttpUrl(apiURL)) throw new Error("APPS_SCRIPT_URL غير آمن (لازم http/https).");

        let payload = { source: "website", type_ar: type };

        if (type === "عرض عقار") {
            payload = {
                ...payload,
                type: "owner_offer",
                owner_name: formData.ownerName || formData.owner_name || formData.fullName || formData.name || "",
                phone: normalizeSaudiPhone(formData.ownerPhone || formData.phone || ""),
                city: formData.city || "",
                neighborhood: formData.neighborhood || formData.district || "",
                property_type: formData.propertyType || formData.property_type || "",
                property_age: formData.propertyAge || formData.property_age || "",
                listing_type: formData.offerType || formData.listing_type || "",
                category: formData.category || "",
                area: formData.area || "",
                price: formData.price || "",
                floors: formData.floors || 0,
                apartments: formData.apartments || 0,
                rooms: formData.rooms || 0,
                bathrooms: formData.bathrooms || 0,
                images_link: formData.imagesUrl || formData.images_link || "",
                google_map: formData.mapUrl || formData.google_map || "",
                owner_notes: formData.ownerNotes || formData.owner_notes || "",
            };
        } else if (type === "lead") {
            payload = {
                ...payload,
                type: "lead",
                name: formData.name || "",
                phone: normalizeSaudiPhone(formData.phone || ""),
                notes: formData.notes || formData.message || "",
                listing_id: formData.listing_id || "",
                title: formData.title || "",
                district: formData.district || "",
                price: formData.price || "",
                property_id: formData.property_id || "",
            };
        } else {
            payload = { ...payload, type: String(type || "general"), ...formData };
        }

        if (type === "lead" && formData.property_id) {
            try {
                const trackResponse = await fetch(`/api/properties/${formData.property_id}/track-inquiry/`, {
                    method: "POST",
                    headers: { "X-CSRFToken": getCookie("csrftoken") || "" },
                    credentials: "same-origin",
                });
                if (trackResponse.ok) {
                    const trackData = await trackResponse.json();
                    payload.counter = trackData.inquiry_count;
                }
            } catch (err) {
                console.error("Tracking failed:", err);
            }
        }

        const res = await fetch(apiURL, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            },
            credentials: "omit",
            body: JSON.stringify(payload),
        });

        const text = await res.text();
        console.log("CRM status:", res.status);
        console.log("CRM response:", text);
        console.log("CRM payload sent:", payload);

        if (!res.ok) throw new Error(`CRM API failed: ${res.status} :: ${text.slice(0, 300)}`);

        const whatsappNumber = WHATSAPP_NUMBER();
        let waText = "";

        if (type === "عرض عقار") {
            waText = `السلام عليكم معاكم ${payload.owner_name || ""} تم إرسال عرض عقار عبر الموقع.`;
        } else if (type === "lead") {
            waText = `السلام عليكم معاك ${payload.name || ""} أرغب في الاستفسار عن ${(payload.title || payload.district || "")} رقم ${(payload.listing_id || "")}`;
        }

        if (typeof window.showSuccessModal === "function") {
            window.showSuccessModal({
                title: type === "lead" ? "استفسارك محل اهتمامنا" : "تم استقبال طلبك بنجاح",
                message:
                    type === "lead"
                        ? "تقديرنا لثقتك بنا، سنرد عليك في أقرب وقت ممكن"
                        : "تم استلام طلبك بنجاح وسيتم التواصل معك قريباً.",
                waCustomMsg: waText,
            });
        }

        if (waText) {
            setTimeout(() => {
                window.location.href = `https://wa.me/${whatsappNumber}?text=${encodeURIComponent(waText)}`;
            }, 2500);
        }

        return true;
    }

    // ===== Request Property -> Django API =====
    function syncRequestPropertyDistricts(formEl) {
        const checked = Array.from(formEl.querySelectorAll('input[name="districts"]:checked')).map(
            (el) => el.value
        );
        const joined = formEl.querySelector("[data-district-joined]");
        if (joined) joined.value = checked.join("، ");

        const selectedBox = formEl.querySelector("[data-district-selected]");
        if (selectedBox) {
            selectedBox.innerHTML = checked.length
                ? checked.map((d) => `<span class="req-district-tag">${d}</span>`).join("")
                : '<span class="req-hint">لم يُختر أي حي بعد</span>';
        }
        return checked;
    }

    function syncRequestPropertyBudgetOptions(formEl) {
        const typeSelect = formEl.querySelector("[data-budget-trigger]");
        const rangeSelect = formEl.querySelector("[data-budget-range]");
        if (!typeSelect || !rangeSelect) return;

        const isRent = String(typeSelect.value || "").includes("إيجار");
        const groups = rangeSelect.querySelectorAll("[data-budget-group]");
        groups.forEach((group) => {
            const isBuyGroup = group.getAttribute("data-budget-group") === "buy";
            const show = isRent ? !isBuyGroup : isBuyGroup;
            group.disabled = !show;
            group.hidden = !show;
        });

        const current = rangeSelect.value;
        let currentOpt = null;
        try {
            currentOpt = rangeSelect.querySelector(`option[value="${CSS.escape(current)}"]`);
        } catch (_) {
            currentOpt = Array.from(rangeSelect.options).find((o) => o.value === current) || null;
        }
        const currentGroup = currentOpt?.closest("[data-budget-group]");
        if (currentGroup && currentGroup.disabled) {
            rangeSelect.value = "";
        }
    }

    function initRequestPropertyFormUI(formEl) {
        if (!formEl || formEl.dataset.reqUiReady === "1") return;
        formEl.dataset.reqUiReady = "1";

        const filter = formEl.querySelector(".req-district-filter");
        const grid = formEl.querySelector("[data-district-grid]");
        if (filter && grid) {
            filter.addEventListener("input", () => {
                const q = filter.value.trim();
                grid.querySelectorAll(".req-district-chip").forEach((chip) => {
                    const text = chip.textContent || "";
                    chip.style.display = !q || text.includes(q) ? "" : "none";
                });
            });
        }

        formEl.querySelectorAll('input[name="districts"]').forEach((cb) => {
            cb.addEventListener("change", () => syncRequestPropertyDistricts(formEl));
        });

        const typeSelect = formEl.querySelector("[data-budget-trigger]");
        if (typeSelect) {
            typeSelect.addEventListener("change", () => syncRequestPropertyBudgetOptions(formEl));
        }

        syncRequestPropertyBudgetOptions(formEl);
        syncRequestPropertyDistricts(formEl);
    }

    function formatRequestPropertyErrors(data) {
        if (!data) return "فشل إرسال الطلب.";
        if (typeof data.error === "string" && data.error) return data.error;
        if (typeof data.message === "string" && data.message && data.success === false) {
            return data.message;
        }
        const errors = data.errors || {};
        const msgs = Object.values(errors).flat().filter(Boolean);
        return msgs.length ? msgs.join("\n") : "فشل إرسال الطلب. راجع البيانات والمحاولة مرة أخرى.";
    }

    async function submitRequestPropertyForm(formEl) {
        const districts = syncRequestPropertyDistricts(formEl);
        if (!districts.length) {
            throw new Error("اختر حياً واحداً على الأقل من أحياء الرياض.");
        }

        const budgetRange = formEl.querySelector("[data-budget-range]");
        if (budgetRange && !String(budgetRange.value || "").trim()) {
            throw new Error("اختر نطاق الميزانية.");
        }

        const fd = new FormData(formEl);
        // تأكيد إرسال الحي كنص موحّد + قائمة
        fd.set("district", districts.join("، "));
        districts.forEach((d) => {
            if (![...fd.getAll("districts")].includes(d)) fd.append("districts", d);
        });

        const csrf = getCookie("csrftoken") || "";
        const res = await fetch("/api/request-property/", {
            method: "POST",
            body: fd,
            credentials: "same-origin",
            headers: {
                ...(csrf ? { "X-CSRFToken": csrf } : {}),
                "X-Requested-With": "XMLHttpRequest",
            },
        });

        const data = await res.json().catch(() => ({}));
        if (!res.ok || data?.ok === false || data?.success === false) {
            console.error("request_property failed:", data);
            throw new Error(formatRequestPropertyErrors(data));
        }

        formEl.reset();
        syncRequestPropertyBudgetOptions(formEl);
        syncRequestPropertyDistricts(formEl);

        if (typeof window.showSuccessModal === "function") {
            const clientName = String(fd.get("client_name") || fd.get("name") || "").trim();
            window.showSuccessModal({
                title: "تم استلام طلبك العقاري بنجاح",
                message: data?.message || "سنقوم بالبحث عن العقار المناسب لمواصفاتك والتواصل معك قريباً.",
                name: clientName,
                waCustomMsg: `السلام عليكم، معك ${clientName || "عميل"}. قمت بإرسال طلب عقار عبر الموقع وأرغب بالمتابعة.`,
            });
        }
        return true;
    }

    // ===== Pagination (Stable) =====
    function setupPagination() {
        const PAGE_SIZE = 6;

        function getCards() {
            return Array.from(document.querySelectorAll("[data-property-card]"));
        }

        function ensureActionsContainer(listRoot) {
            let actions = document.getElementById("propertiesActions");
            if (actions) return actions;

            actions = document.createElement("div");
            actions.id = "propertiesActions";
            actions.style.cssText =
                "display:flex;flex-direction:column;gap:12px;align-items:center;margin:18px auto 0;width:100%;";

            if (listRoot) listRoot.after(actions);
            return actions;
        }

        function ensureLoadMoreButton(state) {
            safeRemoveById("loadMoreBtn");

            const listRoot = state.cards[0]?.parentElement;
            const actions = ensureActionsContainer(listRoot);

            if (!actions) return;

            const btn = document.createElement("button");
            btn.id = "loadMoreBtn";
            btn.type = "button";
            btn.textContent = "عرض المزيد";
            btn.style.cssText = `
        display:flex;align-items:center;justify-content:center;
        width:min(520px, 92%);height:52px;margin:0 auto;
        border-radius:999px;border:1px solid rgba(0,0,0,0.06);
        cursor:pointer;font-weight:700;background:#0b1320;color:#fff;
      `;

            actions.appendChild(btn);

            btn.addEventListener(
                "click",
                () => {
                    const start = state.visibleCount;
                    const end = Math.min(state.visibleCount + state.pageSize, state.total);

                    for (let i = start; i < end; i++) {
                        state.cards[i].style.display = "";
                    }

                    state.visibleCount = end;
                    if (state.visibleCount >= state.total) btn.style.display = "none";
                    if (typeof window.syncListingsAdBannerVisibility === "function") {
                        window.syncListingsAdBannerVisibility();
                    }
                    if (typeof window.syncOffersCardStack === "function") {
                        window.syncOffersCardStack();
                    }
                },
                { passive: true }
            );

            if (state.total <= state.pageSize) btn.style.display = "none";
        }

        function ensureRequestPropertyButton() {
            safeRemoveById("requestPropertyBtn");
            const actions = document.getElementById("propertiesActions");
            if (!actions) return;

            const a = document.createElement("a");
            a.id = "requestPropertyBtn";
            a.href = "/request-property/";
            a.textContent = "اطلب عقارًا بمواصفاتك الآن";
            a.style.cssText = `
        display:flex;align-items:center;justify-content:center;
        width:min(520px, 92%);height:52px;margin:0 auto;
        border-radius:999px;text-decoration:none;cursor:pointer;font-weight:800;
        background:#f3f4f6;color:#111827;border:1px solid #111827;
      `;
            actions.appendChild(a);
        }

        function applyPagination() {
            const cards = getCards();

            if (!cards.length) return;

            cards.forEach((card, idx) => {
                card.style.display = idx < PAGE_SIZE ? "" : "none";
            });

            const state = {
                pageSize: PAGE_SIZE,
                visibleCount: Math.min(PAGE_SIZE, cards.length),
                total: cards.length,
                cards,
            };

            ensureLoadMoreButton(state);
            ensureRequestPropertyButton();
        }

        return { applyPagination };
    }

    // ===== Main DOMContentLoaded =====
    document.addEventListener("DOMContentLoaded", () => {
        console.log("[main.js] loaded ✅");

        // Reveal Animation
        const revealObserver = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add("active");
                        revealObserver.unobserve(entry.target);
                    }
                });
            },
            { threshold: 0.1 }
        );

        // Modal (Inquiry)
        const modal = document.getElementById("inquiry-modal");
        const inquiryForm = document.getElementById("inquiry-form");

        window.openModal = function openModal(prop) {
            if (!modal || !inquiryForm) return;

            inquiryForm.property_id.value = prop.id || "";
            inquiryForm.listing_id.value = prop.id || prop.listing_id || "N/A";
            inquiryForm.listing_title.value = prop.title || "عقار";
            inquiryForm.listing_district.value = prop.district || "غير محدد";
            inquiryForm.listing_price.value = prop.price || "0";

            modal.style.display = "flex";
            modal.classList.add("active");
            document.body.style.overflow = "hidden";
        };

        function closeModal() {
            if (!modal) return;
            modal.classList.remove("active");
            modal.style.display = "none";
            document.body.style.overflow = "auto";
        }

        document.addEventListener("click", (e) => {
            if (e.target === modal || e.target.classList.contains("modal-close")) {
                closeModal();
            }
        });

        // ===== Mobile menu (Updated for Smooth Animation & Overlay) =====
        const menuToggle = document.getElementById("menu-toggle");
        const navLinks = document.getElementById("nav-links");
        const menuOverlay = document.getElementById("menu-overlay");

        if (menuToggle && navLinks) {
            // فتح وإغلاق القائمة عند النقر على الهامبرغر
            menuToggle.onclick = () => {
                navLinks.classList.toggle("active");
                menuToggle.classList.toggle("open");
                if (menuOverlay) menuOverlay.classList.toggle("active");
            };

            // إغلاق القائمة عند النقر على أي رابط
            navLinks.querySelectorAll(".nav-item-link").forEach((link) => {
                link.addEventListener("click", () => {
                    navLinks.classList.remove("active");
                    menuToggle.classList.remove("open");
                    if (menuOverlay) menuOverlay.classList.remove("active");
                });
            });

            // إغلاق القائمة عند النقر على الطبقة الضبابية
            if (menuOverlay) {
                menuOverlay.onclick = () => {
                    navLinks.classList.remove("active");
                    menuToggle.classList.remove("open");
                    menuOverlay.classList.remove("active");
                };
            }
        }

        // Sticky header
        const header = document.querySelector("header");
        if (header) {
            window.addEventListener(
                "scroll",
                () => {
                    if (window.scrollY > 50) header.classList.add("scrolled");
                    else header.classList.remove("scrolled");
                },
                { passive: true }
            );
        }

        // Pagination handler (stable)
        const pager = setupPagination();

        // ===== Listings Fetch & Render =====
        let allListings = [];

        function displayProperties(data) {
            const container = document.getElementById("propertiesList");
            if (!container) return;

            container.innerHTML = "";
            const adCfg = getAdBannerConfig();

            if (!data || data.length === 0) {
                container.innerHTML = buildOffersEmptyState();
                bindOffersEmptyActions(container);
                updateOffersSectionTitle();
                return;
            }

            const isMobileStack = window.matchMedia("(max-width: 768px)").matches;
            const bannerPositions = getAdBannerPositions(adCfg);
            const useBannerSplit = bannerPositions.length > 0;

            // مجموعات sticky منفصلة حول كل بنر حتى لا يُغطى البنر
            let currentGroup = null;
            let groupSeq = 0;

            function ensureStackGroup() {
                if (!useBannerSplit) return null;
                if (!currentGroup) {
                    currentGroup = document.createElement("div");
                    currentGroup.className = "property-stack-group";
                    currentGroup.setAttribute("data-stack-group", String(groupSeq++));
                    container.appendChild(currentGroup);
                }
                return currentGroup;
            }

            function insertBannerAt(slotIndex, afterCount) {
                const wrap = buildListingsAdBanner(adCfg, slotIndex, afterCount);
                if (wrap) {
                    container.appendChild(wrap);
                    currentGroup = null;
                }
            }

            data.forEach((prop, index) => {
                const card = document.createElement("div");
                // على الجوال: sticky stack بدون reveal (transform يكسر sticky)
                card.className = isMobileStack
                    ? "property-card property-card-item"
                    : "property-card reveal";
                card.setAttribute("data-property-card", "");

                const imgUrl = prop.image_url || "/static/img/hero_skyline.png";
                
                // Price logic
                let displayPrice = "السعر عند التواصل";
                let priceClass = "price-hidden";
                if (prop.display_price) {
                    displayPrice = Number(prop.display_price).toLocaleString("ar-SA") + " ريال";
                    priceClass = "price-display";
                }

                function getStatusClass(status) {
                    if (status === 'متاح') return 'badge-success';
                    if (status === 'قيد التفاوض') return 'badge-warning';
                    return 'badge-danger';
                }

                const statusClass = getStatusClass(prop.status);
                const offerType = prop.offer_type || prop.listing_type || "sale";
                const isInvestment = offerType === 'investment' || offerType === 'إستثمار';
                const isSale = offerType === 'sale' || offerType === 'بيع';
                
                card.innerHTML = `
                    <div class="property-thumb">
                        <img src="${imgUrl}" onerror="this.src='/static/img/hero_skyline.png'" alt="${prop.property_type}">
                        <div class="status-badge-pos">
                            <span class="badge ${statusClass}">${prop.status_display || prop.status}</span>
                        </div>
                        <div class="offer-badge" style="background: ${isInvestment ? '#0A0A0A' : (isSale ? '#1B4F9C' : '#4A5568')}; color: ${isInvestment ? '#9DB7E0' : 'white'}; border: ${isInvestment ? '1px solid #9DB7E0' : 'none'};">
                            ${isInvestment ? 'إستثمار' : (isSale ? 'للبيع' : 'للإيجار')}
                        </div>
                    </div>
                    <div class="property-content">
                        <h3 class="property-title">${prop.property_type || 'عقار'} في حي ${prop.district || prop.neighborhood || 'جدة'}</h3>
                        <div class="property-meta" style="flex-wrap: wrap;">
                            <div class="meta-item">
                                <i class="fas fa-map-marker-alt"></i>
                                <span>حي ${prop.district || prop.neighborhood || 'متميز'}</span>
                            </div>
                            <div class="meta-item">
                                <i class="fas fa-ruler-combined"></i>
                                <span>${prop.area} م²</span>
                            </div>
                            ${prop.rooms ? `
                            <div class="meta-item">
                                <i class="fas fa-bed"></i>
                                <span>${prop.rooms} غرف</span>
                            </div>` : ""}
                            <div class="${priceClass}" style="margin-top: 5px; width: 100%;">
                                <i class="fas fa-tag"></i> ${displayPrice}
                            </div>
                        </div>
                        <div style="margin-top: 20px;">
                            <a href="/property/${prop.id}/" class="btn-whatsapp-card" style="text-decoration: none; display: flex; align-items: center; justify-content: center; background: #1B4F9C; color: white;">
                                <i class="fas fa-info-circle" style="margin-left: 8px;"></i> التفاصيل
                            </a>
                        </div>
                    </div>
                `;

                if (!useBannerSplit) {
                    container.appendChild(card);
                } else {
                    ensureStackGroup().appendChild(card);
                }

                if (!isMobileStack) revealObserver.observe(card);

                const afterCount = index + 1;
                const slotIndex = bannerPositions.indexOf(afterCount);
                if (slotIndex >= 0) {
                    insertBannerAt(slotIndex, afterCount);
                }
            });

            // ✅ طبّق pagination بعد الرسم
            pager.applyPagination();
            syncListingsAdBannerVisibility();
            syncOffersCardStack();
            updateOffersSectionTitle();
        }

        const PROPERTY_TYPE_LABELS = {
            شقة: "شقق",
            عمارة: "عمائر",
            فيلا: "فلل",
            قصر: "قصور",
            أرض: "أراضي",
            مزرعة: "مزارع",
            استراحة: "استراحات",
            دور: "أدوار",
            "محل تجاري": "محلات تجارية",
        };

        function getSelectedPropertyType() {
            return document.getElementById("filter-type")?.value || "all";
        }

        function getPropertyTypeLabel(type) {
            if (!type || type === "all") return "";
            return PROPERTY_TYPE_LABELS[type] || type;
        }

        function updateOffersSectionTitle() {
            const title = document.querySelector("#offers .section-title");
            if (!title) return;
            const type = getSelectedPropertyType();
            const label = getPropertyTypeLabel(type);
            title.textContent = label ? `عروض ${label}` : "عروضنا الحالية";
        }

        function buildOffersEmptyState() {
            const type = getSelectedPropertyType();
            const label = getPropertyTypeLabel(type);
            const headline = label
                ? `لا توجد عروض ${label} حالياً`
                : "لا توجد نتائج مطابقة";
            const detail = label
                ? `لم نعثر على عقارات من نوع «${label}» ضمن العروض المنشورة الآن. يمكنك تصفح كل العروض أو إرسال طلب بمواصفاتك وسنساعدك في إيجاد الأنسب.`
                : "جرّب تعديل كلمات البحث أو الفلاتر، أو أرسل لنا طلب عقار بمواصفاتك.";

            return `
                <div class="offers-empty" role="status" aria-live="polite">
                    <div class="offers-empty-glow" aria-hidden="true"></div>
                    <div class="offers-empty-icon" aria-hidden="true">
                        <i class="fas fa-building"></i>
                    </div>
                    <h3 class="offers-empty-title">${headline}</h3>
                    <p class="offers-empty-text">${detail}</p>
                    <div class="offers-empty-actions">
                        <button type="button" class="offers-empty-btn offers-empty-btn--primary" data-clear-offers-filters>
                            عرض كل العروض
                        </button>
                        <a href="/request-property/" class="offers-empty-btn offers-empty-btn--ghost">
                            اطلب عقاراً بمواصفاتك
                        </a>
                    </div>
                </div>
            `;
        }

        function bindOffersEmptyActions(container) {
            const clearBtn = container.querySelector("[data-clear-offers-filters]");
            if (!clearBtn) return;
            clearBtn.addEventListener("click", () => {
                window.filterOffersByPropertyType("all");
            });
        }

        /** يضبط z-index داخل كل مجموعة تكدس على حدة (حتى لا يغطي البنر) */
        function syncOffersCardStack() {
            const list = document.getElementById("propertiesList");
            if (!list) return;

            const isMobile = window.matchMedia("(max-width: 768px)").matches;
            const groups = Array.from(list.querySelectorAll("[data-stack-group]"));
            const scopes = groups.length ? groups : [list];

            scopes.forEach((scope) => {
                const cards = Array.from(scope.querySelectorAll("[data-property-card]")).filter(
                    (c) => c.style.display !== "none"
                );

                cards.forEach((card, index) => {
                    if (!isMobile) {
                        card.classList.remove("property-card-item");
                        card.style.removeProperty("--stack-step");
                        card.style.removeProperty("--stack-z");
                        card.style.removeProperty("z-index");
                        return;
                    }

                    card.classList.add("property-card-item");
                    card.classList.remove("reveal");
                    const step = Math.min(index, 4) * 10;
                    card.style.setProperty("--stack-step", `${step}px`);
                    card.style.setProperty("--stack-z", String(index + 1));
                    card.style.zIndex = String(index + 1);
                });
            });

            list.querySelectorAll("[data-listings-ad-banner]").forEach((banner) => {
                banner.classList.add("listings-ad-banner--stack-break");
                banner.style.zIndex = "20";
            });
        }
        window.syncOffersCardStack = syncOffersCardStack;

        window.addEventListener(
            "resize",
            () => {
                window.requestAnimationFrame(syncOffersCardStack);
            },
            { passive: true }
        );

        function getAdBannerConfig() {
            const el = document.getElementById("site-ad-banner-config");
            const fallback = {
                enabled: false,
                insertEvery: 4,
                maxBanners: 2,
                logoUrl: "/static/img/logo-banner.png?v=2",
                banners: [],
            };
            if (!el) return fallback;
            try {
                const raw = (el.textContent || "").trim();
                const data = raw ? JSON.parse(raw) : {};
                const insertEvery = parseInt(data.insertEvery, 10);
                const maxBanners = parseInt(data.maxBanners, 10);
                return {
                    enabled: Boolean(data.enabled),
                    insertEvery: Number.isFinite(insertEvery) && insertEvery > 0 ? insertEvery : 4,
                    maxBanners: Number.isFinite(maxBanners) && maxBanners > 0 ? Math.min(maxBanners, 2) : 2,
                    logoUrl: data.logoUrl || fallback.logoUrl,
                    banners: Array.isArray(data.banners) ? data.banners : [],
                };
            } catch (err) {
                console.warn("تعذر قراءة إعدادات البنر:", err);
                return fallback;
            }
        }

        function getAdBannerPositions(cfg) {
            if (!cfg?.enabled) return [];
            const every = cfg.insertEvery || 4;
            const max = cfg.maxBanners || 2;
            const positions = [];
            for (let i = 1; i <= max; i += 1) {
                positions.push(every * i);
            }
            return positions;
        }

        function escapeHtml(value) {
            return String(value ?? "")
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;");
        }

        function buildListingsAdBanner(cfg, slotIndex, afterCount) {
            const bannerCfg = cfg.banners?.[slotIndex] || {};
            const theme = bannerCfg.theme || (slotIndex === 0 ? "services" : "request");
            const alt = bannerCfg.alt || "الركن الأوسط للعقارات";
            const linkUrl = (bannerCfg.linkUrl || "").trim();
            const imageUrl = (bannerCfg.imageUrl || "").trim();

            const wrap = document.createElement("aside");
            wrap.className = "listings-ad-banner listings-ad-banner--stack-break";
            wrap.setAttribute("data-listings-ad-banner", "");
            wrap.setAttribute("data-banner-slot", String(slotIndex + 1));
            wrap.setAttribute("data-insert-after", String(afterCount));
            wrap.setAttribute("aria-label", alt);

            let inner;
            if (imageUrl) {
                wrap.classList.add("listings-ad-banner--image");
                const img = document.createElement("img");
                img.src = imageUrl;
                img.alt = alt;
                img.loading = "lazy";
                img.decoding = "async";
                img.className = "listings-ad-banner-photo";
                inner = img;
            } else if (theme === "request") {
                wrap.classList.add("listings-ad-banner--request");
                const panel = document.createElement("div");
                panel.className = "rokna-banner rokna-banner--request";
                panel.innerHTML = `
                    <div class="rokna-banner-request-mark" aria-hidden="true">
                        <i class="fas fa-handshake"></i>
                    </div>
                    <div class="rokna-banner-content">
                        <p class="rokna-banner-kicker">الركن الأوسط للعقارات</p>
                        <h3 class="rokna-banner-title">${escapeHtml(bannerCfg.title || "ما لقيت طلبك؟")}</h3>
                        <p class="rokna-banner-slogan">${escapeHtml(bannerCfg.slogan || "أرسل مواصفاتك ونبحث لك عن العقار الأنسب.")}</p>
                        <span class="rokna-banner-cta">
                            ${escapeHtml(bannerCfg.cta || "اطلب عقاراً الآن")}
                            <i class="fas fa-arrow-left" aria-hidden="true"></i>
                        </span>
                    </div>
                `;
                inner = panel;
            } else {
                wrap.classList.add("listings-ad-banner--brand");
                const panel = document.createElement("div");
                panel.className = "rokna-banner";
                panel.innerHTML = `
                    <div class="rokna-banner-logo-card">
                        <img src="${escapeHtml(cfg.logoUrl)}" alt="شعار الركن الأوسط للعقارات" class="rokna-banner-logo" width="200" height="180" loading="lazy" decoding="async">
                    </div>
                    <div class="rokna-banner-content">
                        <h3 class="rokna-banner-title">${escapeHtml(bannerCfg.title || "الركن الأوسط")}</h3>
                        <p class="rokna-banner-subtitle">للعقارات</p>
                        <p class="rokna-banner-slogan">${escapeHtml(bannerCfg.slogan || "في كل زاوية، فرصة استثمارية.")}</p>
                        <div class="rokna-banner-services" role="list">
                            <span class="rokna-banner-pill" role="listitem">تأجير</span>
                            <span class="rokna-banner-pill" role="listitem">بيع</span>
                            <span class="rokna-banner-pill" role="listitem">إدارة أملاك</span>
                            <span class="rokna-banner-pill" role="listitem">تطوير عقاري</span>
                        </div>
                    </div>
                `;
                inner = panel;
            }

            if (linkUrl) {
                const a = document.createElement("a");
                a.href = linkUrl;
                const isExternal = /^https?:\/\//i.test(linkUrl);
                if (isExternal) {
                    a.target = "_blank";
                    a.rel = "noopener noreferrer";
                }
                a.className = "listings-ad-banner-link";
                a.setAttribute("aria-label", alt);
                a.appendChild(inner);
                wrap.appendChild(a);
            } else {
                wrap.appendChild(inner);
            }
            return wrap;
        }

        function syncListingsAdBannerVisibility() {
            const cards = Array.from(document.querySelectorAll("[data-property-card]"));
            const visible = cards.filter((c) => c.style.display !== "none").length;
            document.querySelectorAll("[data-listings-ad-banner]").forEach((banner) => {
                const after = parseInt(banner.getAttribute("data-insert-after") || "0", 10);
                banner.style.display = visible >= after ? "" : "none";
            });
        }
        window.syncListingsAdBannerVisibility = syncListingsAdBannerVisibility;

        async function fetchProperties(queryString = "") {
            const apiURL = `/api/listings/${queryString}`;
            const container = document.getElementById("propertiesList");
            if (!container) return;

            try {
                const response = await fetch(apiURL);
                if (!response.ok) throw new Error(`Server responded with status: ${response.status}`);

                allListings = await response.json();
                displayProperties(allListings);
                console.log("تم جلب العقارات من الباكند بنجاح ✅");
            } catch (error) {
                console.error("خطأ في جلب البيانات من الباكند:", error);
                container.innerHTML =
                    '<div style="grid-column: 1/-1; text-align: center; padding: 60px; color: #64748b;"><i class="fas fa-exclamation-triangle fa-2x" style="color: #1B4F9C; margin-bottom: 20px;"></i><p style="font-size: 1.2rem;">نعتذر، حدث خطأ أثناء جلب البيانات. يرجى المحاولة لاحقاً.</p></div>';
            }
        }

        // Search + فلترة مضغوطة على الجوال
        const filterBar = document.getElementById("offersFilterBar");
        const filterToggle = document.getElementById("filterBarToggle");
        const filterActiveCount = document.getElementById("filterActiveCount");
        const districtInput = document.getElementById("filter-district-text");

        function countActiveFilters() {
            let n = 0;
            const offerType = document.getElementById("filter-offer-type")?.value;
            const propertyType = document.getElementById("filter-type")?.value;
            const minPrice = document.getElementById("filter-min-price")?.value;
            const maxPrice = document.getElementById("filter-max-price")?.value;
            if (offerType && offerType !== "all") n += 1;
            if (propertyType && propertyType !== "all") n += 1;
            if (minPrice) n += 1;
            if (maxPrice) n += 1;
            return n;
        }

        function syncFilterActiveCount() {
            if (!filterActiveCount) return;
            const n = countActiveFilters();
            if (n > 0) {
                filterActiveCount.hidden = false;
                filterActiveCount.textContent = String(n);
            } else {
                filterActiveCount.hidden = true;
            }
        }

        function syncOffersUrl(params) {
            try {
                const url = new URL(window.location.href);
                ["offer_type", "property_type", "district", "min_price", "max_price"].forEach((key) => {
                    url.searchParams.delete(key);
                });
                params.forEach((value, key) => url.searchParams.set(key, value));
                const qs = url.searchParams.toString();
                const next = `${url.pathname}${qs ? `?${qs}` : ""}#offers`;
                window.history.replaceState({}, "", next);
            } catch (_) {
                /* تجاهل بيئات بدون History API */
            }
        }

        function runOffersSearch(options = {}) {
            const { scroll = true, updateUrl = true } = options;
            const offerType = document.getElementById("filter-offer-type")?.value;
            const propertyType = document.getElementById("filter-type")?.value;
            const district = districtInput?.value;
            const minPrice = document.getElementById("filter-min-price")?.value;
            const maxPrice = document.getElementById("filter-max-price")?.value;

            const params = new URLSearchParams();
            if (offerType && offerType !== "all") params.append("offer_type", offerType);
            if (propertyType && propertyType !== "all") params.append("property_type", propertyType);
            if (district) params.append("district", district);
            if (minPrice) params.append("min_price", minPrice);
            if (maxPrice) params.append("max_price", maxPrice);

            const queryString = params.toString() ? `?${params.toString()}` : "";
            if (updateUrl) syncOffersUrl(params);
            fetchProperties(queryString);
            syncFilterActiveCount();
            updateOffersSectionTitle();

            // على الجوال: أغلق التصفية المتقدمة بعد البحث لتوفير المساحة
            if (filterBar && window.matchMedia("(max-width: 767px)").matches) {
                filterBar.classList.remove("is-open");
                if (filterToggle) filterToggle.setAttribute("aria-expanded", "false");
            }

            if (scroll) {
                const offersSection = document.getElementById("offers");
                if (offersSection) offersSection.scrollIntoView({ behavior: "smooth" });
            }
        }

        window.runOffersSearch = runOffersSearch;

        function syncPropertyTypeButtons(type) {
            const nextType = type || "all";
            document.querySelectorAll(".ptype-btn").forEach((btn) => {
                const btnType = btn.getAttribute("data-property-type") || "all";
                btn.classList.toggle("is-active", btnType === nextType);
            });
        }

        window.filterOffersByPropertyType = function filterOffersByPropertyType(type) {
            const typeSelect = document.getElementById("filter-type");
            const nextType = type || "all";
            if (typeSelect) typeSelect.value = nextType;
            syncPropertyTypeButtons(nextType);
            runOffersSearch({ scroll: true, updateUrl: true });
        };

        if (filterToggle && filterBar) {
            filterToggle.addEventListener("click", () => {
                const open = filterBar.classList.toggle("is-open");
                filterToggle.setAttribute("aria-expanded", open ? "true" : "false");
            });
        }

        ["filter-offer-type", "filter-type", "filter-min-price", "filter-max-price"].forEach((id) => {
            const el = document.getElementById(id);
            if (el) el.addEventListener("change", syncFilterActiveCount);
            if (el) el.addEventListener("input", syncFilterActiveCount);
        });

        const searchBtn = document.getElementById("btn-search");
        const searchBtnAdvanced = document.getElementById("btn-search-advanced");
        if (searchBtn) searchBtn.addEventListener("click", runOffersSearch);
        if (searchBtnAdvanced) searchBtnAdvanced.addEventListener("click", runOffersSearch);

        if (districtInput) {
            districtInput.addEventListener("keydown", (e) => {
                if (e.key === "Enter") {
                    e.preventDefault();
                    runOffersSearch();
                }
            });
        }

        syncFilterActiveCount();

        // ===== lead (inquiry modal) =====
        if (inquiryForm) {
            inquiryForm.addEventListener("submit", async (e) => {
                e.preventDefault();

                const btn = inquiryForm.querySelector('button[type="submit"]');
                const loading = setBtnLoading(btn, '<i class="fas fa-spinner fa-spin"></i> جاري الإرسال...');

                const name = inquiryForm.name?.value || "";
                const phone = normalizeSaudiPhone(inquiryForm.phone?.value || "");

                const listingTitle = inquiryForm.listing_title?.value || "";
                const listingId = inquiryForm.listing_id?.value || "";
                const listingDistrict = inquiryForm.listing_district?.value || "";
                const listingPrice = inquiryForm.listing_price?.value || "";

                const messageText = `الطلب للمعاينة: (${listingTitle})، رقم العقار: ${listingId}، الحي: ${listingDistrict}، السعر: ${listingPrice}`;

                const formData = {
                    name,
                    phone,
                    notes: `استفسار عن عقار: ${listingTitle} (ID: ${listingId})`,
                    listing_id: listingId,
                    title: listingTitle,
                    district: listingDistrict,
                    price: listingPrice,
                    property_id: inquiryForm.property_id?.value || "",
                    message: messageText,
                };

                try {
                    await submitToCRM(formData, "lead");
                    closeModal();
                } catch (err) {
                    console.error("lead -> CRM failed:", err);
                    alert("تعذر حفظ الاستفسار حالياً.");
                } finally {
                    loading.restore();
                }
            });
        }


        // ===== request-property forms (صفحة + مودال) =====
        const requestPropertyForms = document.querySelectorAll(
            "#request-property-form, #request-property-modal-form, form.request-property-form"
        );
        requestPropertyForms.forEach((requestPropertyForm) => {
            initRequestPropertyFormUI(requestPropertyForm);
            requestPropertyForm.addEventListener("submit", async (e) => {
                e.preventDefault();

                const btn = requestPropertyForm.querySelector('button[type="submit"]');
                const loading = setBtnLoading(btn, '<i class="fas fa-spinner fa-spin"></i> جاري الإرسال...');
                const errBox =
                    requestPropertyForm.querySelector(".req-form-errors") ||
                    document.getElementById("request-property-errors");

                if (errBox) {
                    errBox.hidden = true;
                    errBox.textContent = "";
                }

                try {
                    await submitRequestPropertyForm(requestPropertyForm);
                    if (typeof closeRequestModal === "function") {
                        try { closeRequestModal(); } catch (_) { /* ignore */ }
                    }
                } catch (err) {
                    console.error("request_property error:", err);
                    const msg = err?.message || "عذراً، حدث خطأ أثناء إرسال الطلب.";
                    if (errBox) {
                        errBox.hidden = false;
                        errBox.textContent = msg;
                        errBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
                    } else {
                        alert(msg);
                    }
                } finally {
                    loading.restore();
                }
            });
        });

        // ===== property-inquiry-form (backend) =====
        const propertyInquiryForm = document.getElementById("property-inquiry-form");
        if (propertyInquiryForm) {
            propertyInquiryForm.addEventListener("submit", async (e) => {
                e.preventDefault();

                const submitBtn = propertyInquiryForm.querySelector('button[type="submit"]');
                const loading = setBtnLoading(submitBtn, '<i class="fas fa-spinner fa-spin"></i> جاري الإرسال...');

                try {
                    const formData = new FormData(propertyInquiryForm);
                    const response = await fetch(propertyInquiryForm.action, {
                        method: "POST",
                        body: formData,
                        headers: {
                            "X-CSRFToken": getCookie("csrftoken") || "",
                            "X-Requested-With": "XMLHttpRequest",
                            Accept: "application/json",
                        },
                        credentials: "same-origin",
                    });

                    const ct = response.headers.get("content-type") || "";
                    if (!ct.includes("application/json")) {
                        const text = await response.text();
                        throw new Error("Server returned HTML not JSON: " + text.slice(0, 120));
                    }

                    const result = await response.json();

                    if (result.ok) {
                        window.showSuccessModal({
                            title: "تم استلام استفسارك بنجاح",
                            message: result.message,
                            whatsappUrl: result.data ? result.data.whatsapp_url : "",
                        });
                        propertyInquiryForm.reset();
                    } else {
                        throw new Error(result.error || result.message || "حدث خطأ غير متوقع.");
                    }
                } catch (error) {
                    console.error("Inquiry error:", error);
                    alert(error.message || "عذراً، حدث خطأ أثناء إرسال استفسارك. يرجى المحاولة لاحقاً.");
                } finally {
                    loading.restore();
                }
            });
        }

        // ===== syncPropertyData (read only) =====
        function isMissingText(text) {
            const t = (text || "").trim();
            if (!t) return true;
            return /لا يوجد وصف|غير مسجل|غير مسجلة|جاري تحميل الوصف/i.test(t);
        }

        async function syncPropertyData(listingId) {
            if (!listingId) return;

            const webAppUrl = window.SHEET_SYNC_URL;
            if (!webAppUrl) return;

            const finalUrl = `${webAppUrl}?listing_id=${encodeURIComponent(listingId)}`;

            const cacheKey = `sheet_prop_${listingId}`;
            try {
                const cached = sessionStorage.getItem(cacheKey);
                if (cached) {
                    const parsed = JSON.parse(cached);
                    if (parsed?.ts && Date.now() - parsed.ts < 120000 && parsed?.data) {
                        applySheetData(parsed.data);
                        return;
                    }
                }
            } catch { }

            try {
                const response = await fetch(finalUrl, { headers: { Accept: "application/json" } });
                if (!response.ok) throw new Error(`Sync responded: ${response.status}`);

                const data = await response.json();

                try {
                    sessionStorage.setItem(cacheKey, JSON.stringify({ ts: Date.now(), data }));
                } catch { }

                applySheetData(data);
            } catch (error) {
                console.error("Error syncing property data:", error);
            }

            function applySheetData(data) {
                if (!data || !Array.isArray(data) || data.length === 0) return;

                const property = data[0] || {};
                const descEl = document.getElementById("dynamic-description");
                if (descEl && property.property_description) {
                    const currentDesc = descEl.textContent;
                    if (isMissingText(currentDesc)) {
                        descEl.textContent = String(property.property_description);
                        descEl.style.whiteSpace = "pre-line";
                    }
                }
            }
        }

        window.syncPropertyData = syncPropertyData;

        const contactPageForm = document.getElementById("contact-page-form");
        if (contactPageForm) {
            contactPageForm.addEventListener("submit", (e) => window.sendContactForm(e));
        }

        window.sendContactForm = async function (event) {
            event.preventDefault();
            const form = event.currentTarget || event.target;

            const btn = form.querySelector('button[type="submit"]');
            const loading = setBtnLoading(btn, '<i class="fas fa-spinner fa-spin"></i> جاري الإرسال...');
            const errBox = form.querySelector("#contact-form-errors") || form.querySelector(".req-form-errors");
            if (errBox) {
                errBox.hidden = true;
                errBox.textContent = "";
            }

            try {
                const phoneInput = form.querySelector('input[name="phone"]');
                if (phoneInput) {
                    const rawPhone = phoneInput.value || "";
                    if (!isValidSaudiMobile(rawPhone)) {
                        throw new Error("رقم الجوال غير صحيح. اكتب رقم سعودي مثل: 05xxxxxxxx");
                    }
                    // أرسل الصيغة الموحّدة للخادم
                    phoneInput.value = toAsciiDigits(rawPhone).replace(/[^\d+]/g, "");
                    const normalized = normalizeSaudiPhone(rawPhone);
                    if (normalized.startsWith("9665") && normalized.length === 12) {
                        phoneInput.value = "0" + normalized.slice(3);
                    }
                }

                const fd = new FormData(form);
                const csrf = getCookie("csrftoken") || "";

                const response = await fetch("/api/general-contact/", {
                    method: "POST",
                    body: fd,
                    headers: {
                        ...(csrf ? { "X-CSRFToken": csrf } : {}),
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    credentials: "same-origin",
                });

                const result = await response.json().catch(() => ({}));
                if (!response.ok || result?.ok === false || result?.success === false) {
                    console.error("Django API Error:", response.status, result);
                    const msg =
                        result?.error ||
                        result?.message ||
                        (result?.errors && Object.values(result.errors).flat().join("\n")) ||
                        "فشل إرسال الرسالة. تحقق من البيانات وحاول مرة أخرى.";
                    throw new Error(msg);
                }

                const nameField = form.querySelector('input[name="name"]');
                const nameValue = nameField ? nameField.value : "عميل";
                const waMsg = `السلام عليكم، معك ${nameValue}. قمت بإرسال استفسار عبر الموقع وأرغب في التواصل معكم مباشرة.`;
                const waUrl =
                    result?.data?.whatsapp_url ||
                    `https://wa.me/${WHATSAPP_NUMBER()}?text=${encodeURIComponent(waMsg)}`;

                if (typeof window.showSuccessModal === "function") {
                    window.showSuccessModal({
                        title: "شكرًا لتواصلكم معنا.",
                        message: "تم استلام رسالتكم بنجاح. وسيقوم فريقنا بالرد عليكم في أقرب وقت.",
                        whatsappUrl: waUrl
                    });
                }

                form.reset();
            } catch (err) {
                console.error("Contact form error:", err);
                const msg = err?.message || "عذراً، حدث خطأ أثناء إرسال طلبك. يرجى المحاولة لاحقاً.";
                if (errBox) {
                    errBox.hidden = false;
                    errBox.textContent = msg;
                } else {
                    alert(msg);
                }
            } finally {
                loading.restore();
                if (btn && !btn.innerHTML.includes("paper-plane")) {
                    btn.innerHTML = 'إرسال الطلب <i class="fas fa-paper-plane"></i>';
                }
            }
        };

        // ✅ Start — طبّق فلتر الرابط إن وُجد (مثلاً من أقسام الهيرو)
        (function bootListingsFromUrl() {
            const params = new URLSearchParams(window.location.search);
            const offerType = params.get("offer_type");
            const propertyType = params.get("property_type");
            const district = params.get("district");
            const minPrice = params.get("min_price");
            const maxPrice = params.get("max_price");

            if (offerType && document.getElementById("filter-offer-type")) {
                document.getElementById("filter-offer-type").value = offerType;
            }
            if (propertyType && document.getElementById("filter-type")) {
                document.getElementById("filter-type").value = propertyType;
            }
            syncPropertyTypeButtons(propertyType || "all");
            if (district && districtInput) districtInput.value = district;
            if (minPrice && document.getElementById("filter-min-price")) {
                document.getElementById("filter-min-price").value = minPrice;
            }
            if (maxPrice && document.getElementById("filter-max-price")) {
                document.getElementById("filter-max-price").value = maxPrice;
            }

            if (params.toString()) {
                runOffersSearch({ scroll: window.location.hash === "#offers", updateUrl: false });
            } else {
                fetchProperties();
            }
            syncFilterActiveCount();
            updateOffersSectionTitle();
        })();

        // ✅ Activate reveal for existing elements
        document.querySelectorAll(".reveal").forEach((el) => revealObserver.observe(el));
    });
})();