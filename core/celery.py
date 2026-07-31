"""
Celery application bootstrap for Django project.

Uses Redis URL from environment to be Render-friendly.
"""

from __future__ import annotations

import os

from celery import Celery

# Default Django settings module for Celery CLI.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

app = Celery("core")

# Read all CELERY_* settings from Django settings.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks.py in installed apps.
app.autodiscover_tasks()

