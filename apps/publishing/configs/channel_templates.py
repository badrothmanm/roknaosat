"""
Reusable channel configuration templates.

These templates are tenant-agnostic defaults intended to bootstrap
new white-label company configs quickly.
"""

from __future__ import annotations

from typing import Any

from apps.publishing.models import ChannelProvider


def get_channel_template(provider: str) -> dict[str, Any]:
    """
    Return a default template payload for a provider.

    The payload shape matches ChannelConfig JSON fields:
    - selectors
    - settings_json
    """

    provider = (provider or "").strip().lower()
    if provider == ChannelProvider.HARAJ:
        return _haraj_template()
    raise ValueError(f"No template defined for provider={provider}")


def _haraj_template() -> dict[str, Any]:
    # NOTE:
    # Keep these selectors conservative and broadly compatible.
    # Each tenant can override from admin without changing code.
    selectors = {
        "real_estate_option": "text=عرض عقار",
        "fees_checkbox": "input[type='checkbox']",
        "continue_button": "text=استمرار",
        "title_input": "input[name='title'], input[placeholder*='العنوان']",
        "description_textarea": "textarea[name='description'], textarea[placeholder*='وصف']",
        "price_input": "input[name='price'], input[placeholder*='السعر']",
        "images_input": "input[type='file']",
        "city_select": "select[name*='city']",
        "district_select": "select[name*='district']",
        "property_type_select": "select[name*='property']",
        "transaction_select": "select[name*='offer'], select[name*='transaction']",
        "generic_option": "text={text}",
    }
    settings_json = {
        "headless": False,
        "default_timeout_ms": 15000,
        "step_timeout_ms": 20000,
        "slow_mo_ms": 0,
        "stop_before_publish": True,
        "browser_user_data_dir": "",
        "browser_executable_path": "",
        "require_logged_in_session": True,
        "full_auto": True,
        "auto_publish": False,
        "auto_click_continue": True,
        "upload_images": True,
        "map_mode": "default_pin",
        "hold_browser_open_seconds": 20,
    }
    return {"selectors": selectors, "settings_json": settings_json}

