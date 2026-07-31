"""
Publishing orchestrator service.

This module is the single entry-point for creating and dispatching publishing jobs.
Any UI/API/admin action should call this service instead of touching Celery directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.publishing.models import ChannelProvider, JobStatus, PublishingJob
from apps.publishing.tasks import run_publishing_job


@dataclass(frozen=True, slots=True)
class PublishRequest:
    """
    Normalized request payload for creating a publishing job.
    """

    tenant_id: str | int
    provider: str
    payload: dict[str, Any]
    created_by_id: int | None = None
    source_model: str = ""
    source_object_id: str = ""
    priority: int = 5
    max_attempts: int = 3


class PublisherService:
    """
    Orchestrator for publishing jobs.

    Responsibilities:
    - Validate incoming request shape
    - Create PublishingJob row
    - Dispatch Celery task
    """

    @staticmethod
    @transaction.atomic
    def submit(request: PublishRequest) -> PublishingJob:
        """
        Create and dispatch a new PublishingJob.
        """

        provider = str(request.provider).strip().lower()
        if provider not in {choice for choice, _ in ChannelProvider.choices}:
            raise ValueError(f"Unsupported provider: {request.provider}")

        if not isinstance(request.payload, dict):
            raise ValueError("payload must be a dictionary")

        job = PublishingJob.objects.create(
            company_key=str(request.tenant_id),
            provider=provider,
            status=JobStatus.PENDING,
            payload=request.payload,
            created_by_id=request.created_by_id,
            source_model=request.source_model,
            source_object_id=str(request.source_object_id or ""),
            priority=max(0, int(request.priority)),
            max_attempts=max(1, int(request.max_attempts)),
            queued_at=timezone.now(),
        )

        # Dispatch async execution
        run_publishing_job.delay(str(job.id))
        return job

    @staticmethod
    def retry(job_id: str) -> None:
        """
        Requeue an existing job manually (admin/operator action).
        """

        job = PublishingJob.objects.get(pk=job_id)
        if job.is_terminal and job.status != JobStatus.FAILED:
            raise ValueError(f"Job {job_id} is terminal with status={job.status}")

        job.status = JobStatus.PENDING
        job.next_retry_at = timezone.now()
        job.finished_at = None
        job.queued_at = timezone.now()
        job.save(update_fields=["status", "next_retry_at", "finished_at", "queued_at", "updated_at"])
        run_publishing_job.delay(str(job.id))

