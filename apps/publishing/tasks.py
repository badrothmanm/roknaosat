"""
Celery tasks for publishing pipeline.
"""

from __future__ import annotations

import math
from datetime import timedelta
from typing import Any

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.publishing.adapters.haraj_adapter import HarajAdapter
from apps.publishing.configs.config_resolver import (
    ChannelConfigNotFoundError,
    ChannelConfigValidationError,
    resolve_channel_config,
)
from apps.publishing.models import ChannelProvider, JobStatus, PublishingJob


def _compute_retry_delay(attempt_number: int) -> int:
    """
    Exponential backoff with sane cap:
    1 -> 30s, 2 -> 60s, 3 -> 120s ... max 20min
    """

    return min(int(30 * math.pow(2, max(0, attempt_number - 1))), 1200)


def _provider_adapter(provider: str, tenant_id: str) -> Any:
    if provider == ChannelProvider.HARAJ:
        return HarajAdapter(tenant_id=tenant_id)
    raise ValueError(f"No adapter registered for provider={provider}")


@shared_task(
    bind=True,
    max_retries=5,
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_publishing_job(self, job_id: str) -> dict[str, Any]:
    """
    Execute one publishing job with resilient retry logic.

    Flow:
    1) Load & lock job
    2) Resolve and validate channel config (selectors/settings)
    3) Run adapter
    4) Persist final status / retry state
    """

    with transaction.atomic():
        job = PublishingJob.objects.select_for_update().filter(pk=job_id).first()
        if not job:
            return {"status": "missing", "job_id": job_id}
        if job.is_terminal:
            return {"status": "skipped_terminal", "job_id": job_id, "job_status": job.status}

        # Guard against early execution before scheduled retry.
        if job.next_retry_at and job.next_retry_at > timezone.now():
            return {
                "status": "deferred",
                "job_id": job_id,
                "next_retry_at": job.next_retry_at.isoformat(),
            }

        # Resolve config before running adapter (as requested).
        try:
            resolved_cfg = resolve_channel_config(
                tenant_id=job.company_key,
                channel=job.provider,
                config_name="default",
                use_cache=True,
            )
            job.channel_config_id = resolved_cfg.config_id
        except (ChannelConfigNotFoundError, ChannelConfigValidationError) as exc:
            job.mark_failed(
                error_details={
                    "error_type": exc.__class__.__name__,
                    "message": str(exc),
                    "phase": "resolve_channel_config",
                },
                retry_delay_seconds=300,
            )
            return {"status": "failed_config", "job_id": job_id, "error": str(exc)}

        # Mark running increments attempts.
        job.mark_running()

    # Run outside transaction to keep DB locks short.
    try:
        adapter = _provider_adapter(job.provider, tenant_id=job.company_key)
        adapter_result = adapter.publish(job.payload or {})
    except Exception as exc:  # noqa: BLE001
        adapter_result = {
            "status": "failed",
            "message": "Adapter raised unexpected exception",
            "debug": {"error_type": exc.__class__.__name__, "error": str(exc)},
        }

    normalized_status = str((adapter_result or {}).get("status", "")).lower().strip()

    with transaction.atomic():
        job = PublishingJob.objects.select_for_update().get(pk=job_id)
        if normalized_status == JobStatus.REVIEW_READY:
            job.mark_review_ready(result=adapter_result)
            return {"status": "review_ready", "job_id": job_id}

        if normalized_status == JobStatus.SUCCEEDED:
            job.mark_succeeded(result=adapter_result)
            return {"status": "succeeded", "job_id": job_id}

        # Failed path with retry logic
        attempts_used = job.attempts
        can_retry = attempts_used < job.max_attempts
        error_payload = {
            "phase": "adapter_publish",
            "adapter_result": adapter_result,
            "attempt": attempts_used,
        }

        if can_retry:
            delay = _compute_retry_delay(attempts_used)
            job.status = JobStatus.PENDING
            job.finished_at = timezone.now()
            job.error_details = error_payload
            job.next_retry_at = timezone.now() + timedelta(seconds=delay)
            job.save(
                update_fields=[
                    "status",
                    "finished_at",
                    "error_details",
                    "next_retry_at",
                    "updated_at",
                ]
            )
        else:
            job.mark_failed(error_details=error_payload, retry_delay_seconds=0)

    if can_retry:
        raise self.retry(countdown=delay)

    return {"status": "failed", "job_id": job_id, "attempts": attempts_used}

