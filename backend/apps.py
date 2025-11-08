from __future__ import annotations

from django.apps import AppConfig
from django.db.models.signals import post_migrate

from backend.loggers.celery_logger import logger


def setup_periodic_tasks(sender, **kwargs):
    # ✅ Импорты внутри функции — только когда приложения уже загружены
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    try:
        # Создаём интервал: раз в день
        schedule, created = IntervalSchedule.objects.get_or_create(
            every=1,
            period=IntervalSchedule.DAYS,
        )
        if created:
            logger.info("Создан интервал: 1 раз в день")

        # Обновляем или создаём задачу
        task_name = "Удаление истёкших токенов"
        task, created = PeriodicTask.objects.update_or_create(
            name=task_name,
            defaults={
                "interval": schedule,
                "task": "django_rest_passwordreset.tasks.clear_expired_tokens",
                "enabled": True,
            },
        )
        if created:
            logger.info("✅ Создана периодическая задача")
        else:
            logger.info("🔄 Обновлена периодическая задача")

    except Exception as e:
        logger.error(f"❌ Ошибка при создании периодической задачи: {e}")


class BackendConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "backend"

    def ready(self):
        # ✅ Подключаем сигнал только при ready()
        post_migrate.connect(setup_periodic_tasks, sender=self)
