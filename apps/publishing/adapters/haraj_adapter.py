"""
Haraj adapter implementation.

Design goals:
- Implements AdAdapter protocol (from base.py)
- Pulls selectors/settings from DB via config_resolver
- Strong type hints and production-friendly error handling
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from apps.publishing.configs.config_resolver import (
    ChannelConfigNotFoundError,
    ChannelConfigValidationError,
    ResolvedChannelConfig,
    resolve_channel_config,
)
from apps.publishing.models import ChannelProvider

# Assumed existing protocol interface, as requested.
from .base import AdAdapter

logger = logging.getLogger(__name__)

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None
    PlaywrightTimeoutError = Exception

try:
    import requests
except Exception:  # pragma: no cover
    requests = None


class HarajAdapterError(Exception):
    """Base adapter error for Haraj publishing operations."""


@dataclass(slots=True)
class HarajPublishPayload:
    """
    Normalized payload expected by Haraj adapter.
    """

    title: str
    description: str
    price: int | None = None
    city: str | None = None
    district: str | None = None
    transaction_type: str = "sale"  # sale | rent
    property_type: str | None = None
    area: str | None = None
    property_age: str | None = None
    advertiser_type: str | None = None
    buyer_type: str | None = None
    facade: str | None = None
    image_paths: list[str] = field(default_factory=list)
    reference_id: str | None = None


@dataclass(slots=True)
class HarajPublishResult:
    """
    Adapter return object.
    """

    status: str  # review_ready | succeeded | failed
    message: str
    review_url: str | None = None
    external_id: str | None = None
    artifacts: dict[str, str] = field(default_factory=dict)
    debug: dict[str, Any] = field(default_factory=dict)


class HarajAdapter(AdAdapter):
    """
    Haraj adapter.

    Flow:
    1) Resolve tenant/channel configuration from DB
    2) Validate and map payload
    3) Execute semi-automated steps (placeholder methods ready for Playwright integration)
    4) Return review-ready result (no auto final publish)
    """

    provider = ChannelProvider.HARAJ

    def __init__(
        self,
        *,
        tenant_id: str | int,
        config_name: str = "default",
        use_cache: bool = True,
    ) -> None:
        self.tenant_id = tenant_id
        self.config_name = config_name
        self.use_cache = use_cache
        self._resolved: ResolvedChannelConfig | None = None

    def publish(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Execute publishing flow for Haraj.

        Args:
            payload: Raw payload from service/task layer.

        Returns:
            A dict suitable for storing in PublishingJob.result.
        """

        try:
            normalized = self._normalize_payload(payload)
            cfg = self._get_config()

            # NOTE: This is intentionally semi-automated and review-first.
            # Replace _run_flow with Playwright runner integration in next step.
            result = self._run_flow(normalized, cfg)
            return self._to_dict(result)

        except (ChannelConfigNotFoundError, ChannelConfigValidationError) as exc:
            logger.warning("Haraj config error: %s", exc)
            return self._to_dict(
                HarajPublishResult(
                    status="failed",
                    message=str(exc),
                    debug={"error_type": exc.__class__.__name__},
                )
            )
        except HarajAdapterError as exc:
            logger.error("Haraj adapter error: %s", exc)
            return self._to_dict(
                HarajPublishResult(
                    status="failed",
                    message=str(exc),
                    debug={"error_type": "HarajAdapterError"},
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected Haraj adapter failure")
            return self._to_dict(
                HarajPublishResult(
                    status="failed",
                    message="Unexpected adapter failure.",
                    debug={"error_type": exc.__class__.__name__, "error": str(exc)},
                )
            )

    # -------------------------
    # Internal helpers
    # -------------------------

    def _get_config(self) -> ResolvedChannelConfig:
        if self._resolved is None:
            self._resolved = resolve_channel_config(
                tenant_id=self.tenant_id,
                channel=self.provider,
                config_name=self.config_name,
                use_cache=self.use_cache,
            )
        return self._resolved

    def _normalize_payload(self, payload: dict[str, Any]) -> HarajPublishPayload:
        title = str(payload.get("title", "")).strip()
        description = str(payload.get("description", "")).strip()
        if not title:
            raise HarajAdapterError("Payload missing required field: title")
        if not description:
            raise HarajAdapterError("Payload missing required field: description")

        raw_price = payload.get("price")
        price: int | None = None
        if raw_price not in (None, ""):
            try:
                price = int(raw_price)
            except (TypeError, ValueError) as exc:
                raise HarajAdapterError("Payload field price must be numeric") from exc

        transaction_type = str(payload.get("transaction_type", "sale")).strip().lower()
        if transaction_type not in {"sale", "rent"}:
            transaction_type = "sale"

        images = payload.get("image_paths") or []
        if not isinstance(images, list):
            raise HarajAdapterError("Payload field image_paths must be a list")

        return HarajPublishPayload(
            title=title,
            description=description,
            price=price,
            city=(str(payload.get("city", "")).strip() or None),
            district=(str(payload.get("district", "")).strip() or None),
            transaction_type=transaction_type,
            property_type=(str(payload.get("property_type", "")).strip() or None),
            area=(str(payload.get("area", "")).strip() or None),
            property_age=(str(payload.get("property_age", "")).strip() or None),
            advertiser_type=(str(payload.get("advertiser_type", "")).strip() or None),
            buyer_type=(str(payload.get("buyer_type", "")).strip() or None),
            facade=(str(payload.get("facade", "")).strip() or None),
            image_paths=[str(x) for x in images if x],
            reference_id=(str(payload.get("reference_id", "")).strip() or None),
        )

    def _run_flow(self, payload: HarajPublishPayload, cfg: ResolvedChannelConfig) -> HarajPublishResult:
        """
        Execute semi-automated flow in a persistent browser session.

        This binds automation to the tenant's saved browser profile so actions
        are performed under the same Haraj account session.
        """
        if sync_playwright is None:
            raise HarajAdapterError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            )

        user_data_dir = (cfg.settings.browser_user_data_dir or "").strip()
        if not user_data_dir:
            raise HarajAdapterError(
                "Missing settings_json.browser_user_data_dir in ChannelConfig. "
                "Set a persistent browser profile path first."
            )

        profile_dir = Path(user_data_dir).expanduser()
        profile_dir.mkdir(parents=True, exist_ok=True)

        selectors = cfg.selectors
        debug_info = {
            "config_id": cfg.config_id,
            "tenant": cfg.company_key,
            "provider": cfg.provider,
            "config_name": cfg.name,
            "headless": cfg.settings.headless,
            "profile_dir": str(profile_dir),
            "payload_preview": {
                "title": payload.title[:80],
                "price": payload.price,
                "transaction_type": payload.transaction_type,
                "images_count": len(payload.image_paths),
            },
        }

        with sync_playwright() as p:
            launch_kwargs: dict[str, Any] = {
                "user_data_dir": str(profile_dir),
                "headless": cfg.settings.headless,
                "slow_mo": cfg.settings.slow_mo_ms,
            }
            if cfg.settings.browser_executable_path:
                launch_kwargs["executable_path"] = cfg.settings.browser_executable_path

            context = self._launch_persistent_with_retry(p, launch_kwargs, profile_dir)
            page = context.new_page()
            page.set_default_timeout(cfg.settings.default_timeout_ms)
            try:
                page.goto("https://haraj.com.sa/post", wait_until="domcontentloaded")
                page.wait_for_timeout(2500)

                if cfg.settings.require_logged_in_session and self._looks_logged_out(page):
                    artifacts = self._capture_debug_artifacts(page, "logged_out")
                    self._hold_browser_if_needed(cfg)
                    self._safe_close_context(context)
                    return HarajPublishResult(
                        status="failed",
                        message=(
                            "Haraj session is not logged in for this profile. "
                            "Log in once using the same browser_user_data_dir, then retry."
                        ),
                        review_url=page.url,
                        artifacts=artifacts,
                        debug=debug_info,
                    )

                # Step 1: property path + fees
                self._safe_click(page, selectors.real_estate_option)
                self._safe_click_any(page, ["text=عرض عقار", "text=عقار", "text=عقارات"])
                self._safe_check(page, selectors.fees_checkbox)
                self._safe_check_any(page, ["input[type='checkbox']"])
                if cfg.settings.auto_click_continue:
                    self._click_continue_robust(page, selectors.continue_button)

                # Step 2: optional map step
                if cfg.settings.map_mode == "default_pin":
                    self._try_default_map_pin(page, selectors.continue_button, cfg.settings.auto_click_continue)

                # Step 3: form fill
                self._safe_fill(page, selectors.title_input, payload.title)
                self._safe_fill(page, selectors.description_textarea, payload.description)
                if payload.price:
                    self._safe_fill(page, selectors.price_input, str(payload.price))
                selection_debug = self._fill_classification_fields(page, payload, selectors)
                debug_info["classification"] = selection_debug
                details_debug = self._fill_additional_required_fields(page, payload)
                debug_info["details"] = details_debug

                # Step 4: images upload (supports local paths + remote URLs)
                uploaded_count = 0
                if cfg.settings.upload_images and payload.image_paths:
                    image_selector = selectors.images_input or "input[type='file']"
                    uploaded_count = self._upload_images(page, image_selector, payload.image_paths)
                    if uploaded_count > 0:
                        self._wait_images_uploaded(page)
                    elif self._is_image_step(page):
                        # We are already on image step; retry with chooser path.
                        uploaded_count = self._upload_images(page, "input[type='file']", payload.image_paths)
                        if uploaded_count > 0:
                            self._wait_images_uploaded(page)
                debug_info["uploaded_images"] = uploaded_count

                # Step 5: continue navigation
                if cfg.settings.auto_click_continue:
                    self._click_continue_robust(page, selectors.continue_button)
                    self._click_continue_robust(page, selectors.continue_button)

                # Step 6: auto publish (optional)
                published = False
                if cfg.settings.full_auto and cfg.settings.auto_publish:
                    published = self._try_publish_now(page)
                debug_info["published"] = published
                debug_info["current_url"] = page.url

                review_url = page.url
                debug_info["review_url"] = review_url
                debug_info["note"] = (
                    "Full-auto publish attempted."
                    if (cfg.settings.full_auto and cfg.settings.auto_publish)
                    else "Flow reached review stage."
                )

                # If still on initial post URL, selectors likely mismatched: return a clear failure.
                stuck_on_start = (
                    "/post" in (page.url or "").lower()
                    and not published
                    and uploaded_count == 0
                    and not self._is_known_progress_step(page)
                )
                if stuck_on_start:
                    artifacts = self._capture_debug_artifacts(page, "stuck_on_start")
                    self._hold_browser_if_needed(cfg)
                    self._safe_close_context(context)
                    return HarajPublishResult(
                        status="failed",
                        message=(
                            "Automation did not progress beyond Haraj start page. "
                            "Update ChannelConfig selectors to match current Haraj UI."
                        ),
                        review_url=review_url,
                        artifacts=artifacts,
                        debug=debug_info,
                    )

                self._hold_browser_if_needed(cfg)
                artifacts = self._capture_debug_artifacts(page, "flow_end")
                self._safe_close_context(context)
                return HarajPublishResult(
                    status="succeeded" if published else "review_ready",
                    message=(
                        "Haraj publish submitted automatically."
                        if published
                        else "Haraj draft opened with persistent session and base fields applied."
                    ),
                    review_url=review_url,
                    artifacts=artifacts,
                    debug=debug_info,
                )
            except Exception as exc:  # noqa: BLE001
                debug_info["flow_exception"] = {"type": exc.__class__.__name__, "error": str(exc)}
                artifacts = self._capture_debug_artifacts(page, "flow_exception")
                self._hold_browser_if_needed(cfg)
                self._safe_close_context(context)
                if exc.__class__.__name__ == "TargetClosedError":
                    return HarajPublishResult(
                        status="review_ready",
                        message="Browser was closed during automation; preserving progress at current step.",
                        review_url=page.url if page else None,
                        artifacts=artifacts,
                        debug=debug_info,
                    )
                return HarajPublishResult(
                    status="failed",
                    message=f"Haraj flow crashed: {exc.__class__.__name__}",
                    review_url=page.url if page else None,
                    artifacts=artifacts,
                    debug=debug_info,
                )

    @staticmethod
    def _looks_logged_out(page) -> bool:
        content = (page.content() or "")
        return ("تسجيل الدخول" in content) or ("login" in page.url.lower())

    @staticmethod
    def _safe_click(page, selector: str) -> None:
        try:
            loc = page.locator(selector).first
            if loc.count() > 0:
                loc.click(timeout=3000)
        except PlaywrightTimeoutError:
            return
        except Exception:
            return

    @staticmethod
    def _safe_check(page, selector: str) -> None:
        try:
            loc = page.locator(selector).first
            if loc.count() > 0 and not loc.is_checked():
                loc.check(timeout=3000)
        except Exception:
            return

    @staticmethod
    def _safe_fill(page, selector: str, value: str) -> None:
        if not value:
            return
        try:
            loc = page.locator(selector).first
            if loc.count() > 0:
                loc.fill(value, timeout=4000)
        except Exception:
            return

    @staticmethod
    def _safe_click_any(page, selectors: list[str]) -> None:
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    loc.click(timeout=2500)
                    return
            except Exception:
                continue

    @staticmethod
    def _safe_check_any(page, selectors: list[str]) -> None:
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and not loc.is_checked():
                    loc.check(timeout=2500)
                    return
            except Exception:
                continue

    @staticmethod
    def _try_default_map_pin(page, continue_selector: str, auto_continue: bool) -> None:
        """
        Best-effort fallback for map step:
        - click map center area if visible
        - continue if enabled
        """
        try:
            map_candidates = [
                "canvas.mapboxgl-canvas",
                "div[class*='map'] canvas",
                "div[class*='leaflet']",
            ]
            for sel in map_candidates:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    box = loc.bounding_box()
                    if box:
                        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                        break
            if auto_continue:
                HarajAdapter._safe_click(page, continue_selector)
        except Exception:
            return

    @staticmethod
    def _upload_images(page, file_input_selector: str, image_sources: list[str]) -> int:
        """
        Upload images from local paths or remote URLs.
        Remote URLs are downloaded to local cache files before upload.
        """
        local_files = HarajAdapter._prepare_local_image_files(image_sources[:20])
        if not local_files:
            return 0

        # Path A: direct input[type=file]
        selector_candidates = [
            file_input_selector,
            "input[type='file']",
            "input[type='file'][multiple]",
        ]
        for sel in selector_candidates:
            try:
                locs = page.locator(sel)
                count = locs.count()
                if count <= 0:
                    continue
                for i in range(count):
                    try:
                        locs.nth(i).set_input_files(local_files)
                        return len(local_files)
                    except Exception:
                        continue
            except Exception:
                continue

        # Path B: click upload button and capture file chooser.
        button_candidates = [
            "text=اختر الصور",
            "button:has-text('اختر الصور')",
            "text=تحميل الصور",
        ]
        for btn in button_candidates:
            try:
                with page.expect_file_chooser(timeout=3500) as chooser_info:
                    page.locator(btn).first.click(timeout=3000)
                chooser_info.value.set_files(local_files)
                return len(local_files)
            except Exception:
                continue
        return 0

    @staticmethod
    def _prepare_local_image_files(image_sources: list[str]) -> list[str]:
        """
        Resolve sources into local file paths acceptable by browser upload.
        """
        local_files: list[str] = []
        cache_dir = Path("tmp") / "publishing_upload_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        for idx, src in enumerate(image_sources):
            src = (src or "").strip()
            if not src:
                continue
            p = Path(src)
            if p.exists():
                local_files.append(str(p))
                continue
            if src.startswith("http://") or src.startswith("https://"):
                if requests is None:
                    continue
                try:
                    r = requests.get(src, timeout=25)
                    if r.status_code != 200 or not r.content:
                        continue
                    suffix = ".jpg"
                    ctype = (r.headers.get("content-type") or "").lower()
                    if "png" in ctype:
                        suffix = ".png"
                    elif "webp" in ctype:
                        suffix = ".webp"
                    out = cache_dir / f"img_{int(time.time())}_{idx}{suffix}"
                    out.write_bytes(r.content)
                    local_files.append(str(out))
                except Exception:
                    continue
        return local_files

    @staticmethod
    def _try_publish_now(page) -> bool:
        """
        Try final submit with common button labels.
        """
        publish_selectors = [
            "text=نشر الإعلان",
            "text=نشر",
            "button[type='submit']",
        ]
        for sel in publish_selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    loc.click(timeout=4000)
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _wait_images_uploaded(page) -> None:
        """
        Best-effort wait until 'no images uploaded' hint disappears.
        """
        try:
            empty_hint = page.locator("text=لم يتم رفع أي صور بعد").first
            if empty_hint.count() > 0:
                empty_hint.wait_for(state="hidden", timeout=12000)
        except Exception:
            return

    @staticmethod
    def _fill_classification_fields(page, payload: HarajPublishPayload, selectors) -> dict[str, Any]:
        """
        Fill required classification fields (city/district/property/transaction) when present.
        """
        result: dict[str, Any] = {
            "city": False,
            "district": False,
            "property_type": False,
            "transaction_type": False,
        }

        city_value = HarajAdapter._normalize_city_value(payload.city)
        district_value = (payload.district or "").strip()
        property_value = (payload.property_type or "").strip()
        transaction_value = "بيع" if payload.transaction_type == "sale" else "إيجار"

        if selectors.city_select and city_value:
            result["city"] = HarajAdapter._safe_pick_option(page, selectors.city_select, city_value, selectors.generic_option)
        if not result["city"] and city_value:
            result["city"] = HarajAdapter._pick_named_select_value(page, ["المدينة", "المنطقة"], city_value)
        if selectors.district_select and district_value:
            result["district"] = HarajAdapter._safe_pick_option(
                page, selectors.district_select, district_value, selectors.generic_option
            )
        if not result["district"] and district_value:
            result["district"] = HarajAdapter._pick_named_select_value(page, ["الحي"], district_value)
        if selectors.property_type_select and property_value:
            result["property_type"] = HarajAdapter._safe_pick_option(
                page, selectors.property_type_select, property_value, selectors.generic_option
            )
        if not result["property_type"] and property_value:
            result["property_type"] = HarajAdapter._pick_named_select_value(page, ["نوع العقار", "العقار"], property_value)
        if selectors.transaction_select and transaction_value:
            result["transaction_type"] = HarajAdapter._safe_pick_option(
                page, selectors.transaction_select, transaction_value, selectors.generic_option
            )
        if not result["transaction_type"] and transaction_value:
            result["transaction_type"] = HarajAdapter._pick_named_select_value(
                page, ["نوع العملية", "نوع العرض"], transaction_value
            )

        return result

    @staticmethod
    def _fill_additional_required_fields(page, payload: HarajPublishPayload) -> dict[str, Any]:
        """
        Fill extra required fields often shown after image upload in Haraj form.
        """
        result: dict[str, Any] = {
            "advertiser_type": False,
            "buyer_type": False,
            "area": False,
            "property_age": False,
            "facade": False,
        }

        adv_type = (payload.advertiser_type or "مالك").strip()
        buyer_type = (payload.buyer_type or "سكني").strip()
        facade = (payload.facade or "شمالية").strip()

        result["advertiser_type"] = HarajAdapter._safe_click_text(page, adv_type)
        result["buyer_type"] = HarajAdapter._safe_click_text(page, buyer_type)
        result["facade"] = HarajAdapter._pick_named_select_value(
            page, ["الواجهة", "واجهة"], facade
        )

        if payload.area:
            result["area"] = HarajAdapter._fill_near_label(page, ["المساحة"], payload.area)
        if payload.property_age:
            result["property_age"] = HarajAdapter._fill_near_label(page, ["عمر العقار"], payload.property_age)

        return result

    @staticmethod
    def _normalize_city_value(raw_city: str | None) -> str:
        if not raw_city:
            return ""
        value = raw_city.strip()
        mapping = {
            "taif": "الطائف",
            "riyadh": "الرياض",
            "jeddah": "جدة",
            "dammam": "الدمام",
            "makkah": "مكة",
            "madinah": "المدينة",
            "khobar": "الخبر",
        }
        return mapping.get(value.lower(), value)

    @staticmethod
    def _safe_pick_option(page, open_selector: str, value_text: str, generic_option_selector: str | None) -> bool:
        """
        Open a select/dropdown and choose option by visible text.
        """
        value_text = (value_text or "").strip()
        if not value_text:
            return False

        try:
            opener = page.locator(open_selector).first
            if opener.count() <= 0:
                return False
            opener.click(timeout=3500)
            page.wait_for_timeout(600)
        except Exception:
            return False

        option_selectors: list[str] = []
        if generic_option_selector and "{text}" in generic_option_selector:
            option_selectors.append(generic_option_selector.replace("{text}", value_text))
        option_selectors.extend(
            [
                f"text={value_text}",
                f"li:has-text('{value_text}')",
                f"button:has-text('{value_text}')",
                f"[role='option']:has-text('{value_text}')",
            ]
        )
        for sel in option_selectors:
            try:
                opt = page.locator(sel).first
                if opt.count() > 0 and opt.is_visible():
                    opt.click(timeout=3000)
                    page.wait_for_timeout(500)
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _safe_click_text(page, text_value: str) -> bool:
        if not text_value:
            return False
        selectors = [
            f"button:has-text('{text_value}')",
            f"[role='button']:has-text('{text_value}')",
            f"text={text_value}",
        ]
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    loc.click(timeout=2500)
                    page.wait_for_timeout(350)
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _fill_near_label(page, labels: list[str], value: str) -> bool:
        """
        Try to fill input located in same field container near a label text.
        """
        value = (value or "").strip()
        if not value:
            return False
        for label in labels:
            try:
                # Preferred: semantic container relation.
                input_loc = page.locator(
                    f"xpath=//*[contains(normalize-space(.), '{label}')]/ancestor::*[1]//input[not(@type='hidden')]"
                ).first
                if input_loc.count() > 0 and input_loc.is_visible():
                    input_loc.fill(value, timeout=2500)
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _pick_named_select_value(page, label_names: list[str], value: str) -> bool:
        """
        Open select near label then choose value by text.
        """
        value = (value or "").strip()
        if not value:
            return False
        for label in label_names:
            try:
                opener = page.locator(
                    f"xpath=//*[contains(normalize-space(.), '{label}')]/ancestor::*[1]//*[self::button or self::div][contains(@class,'select') or contains(@class,'dropdown') or @role='button']"
                ).first
                if opener.count() > 0 and opener.is_visible():
                    opener.click(timeout=2500)
                    page.wait_for_timeout(400)
                    if HarajAdapter._safe_click_text(page, value):
                        return True
            except Exception:
                continue
        return False

    @staticmethod
    def _is_image_step(page) -> bool:
        try:
            content = page.content() or ""
            return ("تحميل الصور" in content) or ("اختر الصور" in content)
        except Exception:
            return False

    @staticmethod
    def _is_known_progress_step(page) -> bool:
        """
        Haraj uses same /post URL across steps, so detect progress by page content.
        """
        try:
            content = page.content() or ""
            markers = [
                "تحميل الصور",
                "اختر الصور",
                "إكمال اعلان",
                "إكمال إعلان",
                "تفاصيل الإعلان",
                "لم يتم رفع أي صور بعد",
            ]
            return any(m in content for m in markers)
        except Exception:
            return False

    @staticmethod
    def _click_continue_robust(page, continue_selector: str | None = None) -> bool:
        """
        Click next/continue using multiple selectors and only when visible.
        """
        candidates: list[str] = []
        if continue_selector:
            candidates.append(continue_selector)
        candidates.extend(
            [
                "button:has-text('استمرار')",
                "text=استمرار",
                "button:has-text('التالي')",
                "[role='button']:has-text('استمرار')",
            ]
        )

        for sel in candidates:
            try:
                locs = page.locator(sel)
                for i in range(locs.count()):
                    btn = locs.nth(i)
                    if btn.is_visible() and btn.is_enabled():
                        btn.scroll_into_view_if_needed(timeout=1500)
                        btn.click(timeout=3000)
                        page.wait_for_timeout(1000)
                        return True
            except Exception:
                continue
        return False

    @staticmethod
    def _hold_browser_if_needed(cfg: ResolvedChannelConfig) -> None:
        """
        Keep browser visible briefly for troubleshooting in headed mode.
        """
        if cfg.settings.headless:
            return
        seconds = max(0, int(cfg.settings.hold_browser_open_seconds or 0))
        if seconds > 0:
            time.sleep(seconds)

    @staticmethod
    def _capture_debug_artifacts(page, label: str) -> dict[str, str]:
        """
        Save screenshot and html snapshot for failed/terminal steps.
        """
        out_dir = Path("tmp") / "publishing_debug"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = str(int(time.time()))
        safe_label = (label or "step").replace(" ", "_")
        shot_path = out_dir / f"{safe_label}_{ts}.png"
        html_path = out_dir / f"{safe_label}_{ts}.html"
        artifacts: dict[str, str] = {}
        try:
            page.screenshot(path=str(shot_path), full_page=True)
            artifacts["screenshot"] = str(shot_path)
        except Exception:
            pass
        try:
            html_path.write_text(page.content() or "", encoding="utf-8")
            artifacts["html"] = str(html_path)
        except Exception:
            pass
        return artifacts

    @staticmethod
    def _safe_close_context(context) -> None:
        try:
            context.close()
        except Exception:
            return

    @staticmethod
    def _launch_persistent_with_retry(p, launch_kwargs: dict[str, Any], profile_dir: Path):
        """
        Launch persistent context with one retry after cleaning stale profile locks.
        """
        HarajAdapter._kill_stale_playwright_profile_processes(profile_dir)
        try:
            return p.chromium.launch_persistent_context(**launch_kwargs)
        except Exception as exc:  # noqa: BLE001
            if exc.__class__.__name__ != "TargetClosedError":
                raise
            HarajAdapter._kill_stale_playwright_profile_processes(profile_dir)
            HarajAdapter._cleanup_profile_locks(profile_dir)
            time.sleep(1.0)
            return p.chromium.launch_persistent_context(**launch_kwargs)

    @staticmethod
    def _cleanup_profile_locks(profile_dir: Path) -> None:
        """
        Remove stale Chromium singleton lock files from profile directory.
        """
        lock_names = [
            "SingletonLock",
            "SingletonCookie",
            "SingletonSocket",
            "lockfile",
        ]
        for name in lock_names:
            p = profile_dir / name
            try:
                if p.exists():
                    p.unlink(missing_ok=True)
            except Exception:
                continue

    @staticmethod
    def _kill_stale_playwright_profile_processes(profile_dir: Path) -> None:
        """
        On Windows, terminate stale Playwright chromium processes using same profile.
        """
        try:
            profile = str(profile_dir).replace("\\", "\\\\")
            cmd = (
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.Name -eq 'chrome.exe' -and "
                "$_.CommandLine -match 'ms-playwright\\\\chromium' -and "
                f"$_.CommandLine -match '{profile}' }} | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            return

    @staticmethod
    def _to_dict(result: HarajPublishResult) -> dict[str, Any]:
        return {
            "status": result.status,
            "message": result.message,
            "review_url": result.review_url,
            "external_id": result.external_id,
            "artifacts": result.artifacts,
            "debug": result.debug,
        }

