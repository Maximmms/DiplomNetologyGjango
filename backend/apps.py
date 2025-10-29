from __future__ import annotations

from django.apps import AppConfig


class BackendConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "backend"

    def ready(self):
        from django.conf import settings

        from backend.tasks import create_periodic_task

        if settings.DEBUG:
            create_periodic_task()
