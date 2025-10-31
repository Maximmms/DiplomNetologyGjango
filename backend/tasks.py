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
        # Создаём или получаем интервал
        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=1,
            period=IntervalSchedule.DAYS,
        )

        # Проверяем существование задачи
        try:
            task = PeriodicTask.objects.get(name="Удаление истёкших токенов")

            # Проверяем, нужно ли обновлять задачу
            needs_update = (
                task.interval != schedule
                or task.task != "backend.tasks.delete_expired_tokens"
                or not task.enabled
                or task.one_off
            )

            if needs_update:
                task.interval = schedule
                task.task = "backend.tasks.delete_expired_tokens"
                task.enabled = True
                task.one_off = False
                task.save()
                logger.info(
                    "🔄 Периодическая задача 'Удаление истёкших токенов' обновлена."
                )
            else:
                logger.info(
                    "✅ Периодическая задача 'Удаление истёкших токенов' уже актуальна."
                )

        except PeriodicTask.DoesNotExist:
            # Создаём новую задачу
            task = PeriodicTask.objects.create(
                name="Удаление истёкших токенов",
                task="backend.tasks.delete_expired_tokens",
                interval=schedule,
                one_off=False,
                enabled=True,
            )
            logger.info("✅ Периодическая задача 'Удаление истёкших токенов' создана.")

        return task

    except Exception as e:
        logger.error(f"❌ Ошибка при создании периодической задачи: {e}")
        return None
