"""
Channel configuration resolver for publishing adapters.

This module provides:
1) Fast config retrieval from DB (with cache)
2) Strict selector validation using Pydantic
3) A stable API suitable for Celery tasks
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.cache import cache

from apps.publishing.models import ChannelConfig

try:
    from pydantic import BaseModel, ConfigDict, Field, ValidationError
except Exception as exc:  # pragma: no cover - explicit runtime guidance
    raise RuntimeError(
        "Pydantic is required for apps.publishing.configs.config_resolver. "
        "Install it with: pip install pydantic"
    ) from exc


class SelectorSchema(BaseModel):
    """
    Validates the minimum required selectors for Haraj channel automation.
    You can extend this schema over time without changing caller code.
    """

    model_config = ConfigDict(extra="allow")

    real_estate_option: str = Field(min_length=1)
    fees_checkbox: str = Field(min_length=1)
    continue_button: str = Field(min_length=1)
    title_input: str = Field(min_length=1)
    description_textarea: str = Field(min_length=1)
    price_input: str = Field(min_length=1)

    # Optional but commonly used fields
    images_input: str | None = None
    city_select: str | None = None
    district_select: str | None = None
    property_type_select: str | None = None
    transaction_select: str | None = None
    generic_option: str | None = None


class AdapterSettingsSchema(BaseModel):
    """
    Optional runtime settings to tune automation behavior.
    """

    model_config = ConfigDict(extra="allow")

    headless: bool = False
    default_timeout_ms: int = 15000
    step_timeout_ms: int = 20000
    stop_before_publish: bool = True
    slow_mo_ms: int = 0
    browser_user_data_dir: str | None = None
    browser_executable_path: str | None = None
    require_logged_in_session: bool = True
    full_auto: bool = False
    auto_publish: bool = False
    auto_click_continue: bool = True
    upload_images: bool = True
    map_mode: str = "default_pin"  # default_pin | skip
    hold_browser_open_seconds: int = 20


@dataclass(frozen=True, slots=True)
class ResolvedChannelConfig:
    """
    Final validated and typed config consumed by adapters.
    """

    config_id: str
    company_key: str
    provider: str
    name: str
    selectors: SelectorSchema
    settings: AdapterSettingsSchema


class ChannelConfigNotFoundError(Exception):
    """Raised when no active ChannelConfig is found for company/provider."""


class ChannelConfigValidationError(Exception):
    """Raised when stored JSON cannot pass Pydantic validation."""


def _cache_key(company_key: str, channel: str, config_name: str) -> str:
    return f"publishing:channel_config:v1:{company_key}:{channel}:{config_name}"


def resolve_channel_config(
    *,
    tenant_id: str | int,
    channel: str,
    config_name: str = "default",
    use_cache: bool = True,
    cache_ttl_seconds: int = 120,
) -> ResolvedChannelConfig:
    """
    Resolve channel configuration for a specific tenant/channel quickly.

    Args:
        tenant_id: Tenant/company identifier (stored as company_key in DB).
        channel: Provider channel slug (e.g. "haraj").
        config_name: Named config variant (default: "default").
        use_cache: Enable cache lookup for Celery-scale throughput.
        cache_ttl_seconds: Cache TTL.

    Returns:
        ResolvedChannelConfig

    Raises:
        ChannelConfigNotFoundError
        ChannelConfigValidationError
    """

    company_key = str(tenant_id)
    key = _cache_key(company_key, channel, config_name)

    if use_cache:
        cached: ResolvedChannelConfig | None = cache.get(key)
        if cached is not None:
            return cached

    row = (
        ChannelConfig.objects.filter(
            company_key=company_key,
            provider=channel,
            name=config_name,
            is_active=True,
        )
        .only("id", "company_key", "provider", "name", "selectors", "settings_json")
        .first()
    )
    if not row:
        raise ChannelConfigNotFoundError(
            f"No active ChannelConfig for company_key={company_key}, channel={channel}, name={config_name}"
        )

    try:
        selectors = SelectorSchema.model_validate(row.selectors or {})
        settings = AdapterSettingsSchema.model_validate(row.settings_json or {})
    except ValidationError as exc:
        raise ChannelConfigValidationError(
            f"Invalid ChannelConfig JSON for id={row.id}: {exc}"
        ) from exc

    resolved = ResolvedChannelConfig(
        config_id=str(row.id),
        company_key=row.company_key,
        provider=row.provider,
        name=row.name,
        selectors=selectors,
        settings=settings,
    )

    if use_cache:
        cache.set(key, resolved, timeout=cache_ttl_seconds)
    return resolved


def clear_channel_config_cache(*, tenant_id: str | int, channel: str, config_name: str = "default") -> None:
    """
    Invalidate cache entry after ChannelConfig updates from admin/API.
    """

    cache.delete(_cache_key(str(tenant_id), channel, config_name))

