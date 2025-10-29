from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone
from django_celery_beat.models import IntervalSchedule, PeriodicTask
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

logger = logging.getLogger(__name__)

@shared_task
def delete_expired_tokens():
    from jwt_tokens.logger import logger as jwt_logger

    expired_threshold = timezone.now() - timedelta(days=2)
    expired_tokens = OutstandingToken.objects.filter(expires_at__lt=expired_threshold)
    count_deleted = expired_tokens.count()
    expired_tokens.delete()

    jwt_logger.info(f"Удалено {count_deleted} истёкших токенов")


def create_periodic_task():
    try:
        # Создаём уникальный интервал
        schedule, created = IntervalSchedule.objects.get_or_create(
            every=1,
            period=IntervalSchedule.DAYS,
            defaults={"name": "День для удаления токенов"},
        )

        # Создаём или получаем периодическую задачу
        task, created = PeriodicTask.objects.get_or_create(
            name="Удаление истёкших токенов",
            defaults={
                "task": "backend.tasks.delete_expired_tokens",
                "interval": schedule,
                "one_off": False,
                "enabled": True,
            }
        )

        if created:
            logger.info("Периодическая задача 'Удаление истёкших токенов' создана.")
        else:
            logger.info("Периодическая задача 'Удаление истёкших токенов' уже существует.")

    except Exception as e:
        logger.error(f"Ошибка при создании периодической задачи: {e}")