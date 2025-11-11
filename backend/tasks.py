from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.core.mail import send_mail as django_send_mail
from django.utils import timezone
from django_celery_beat.models import IntervalSchedule, PeriodicTask
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from DiplomNetologyGjango import settings


@shared_task
def delete_expired_tokens():
    from backend.loggers.jwt_token_logger import logger as jwt_logger

    expired_threshold = timezone.now() - timedelta(days=2)
    expired_tokens = OutstandingToken.objects.filter(expires_at__lt=expired_threshold)
    count_deleted = expired_tokens.count()
    expired_tokens.delete()

    jwt_logger.info(f"Удалено {count_deleted} истёкших токенов")

@shared_task(bind=True)
def send_email_confirmation(self, email: str, subject: str, message: str, from_email=None):
    from backend.loggers.mail_send_logger import logger as email_logger
    """
    Асинхронная задача с повтоными попытками отправки кода подтверждения на email.
    """

    if not from_email:
        from_email = settings.DEFAULT_FROM_EMAIL

    try:
        sent = django_send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[email],
            fail_silently=False,
        )
        if sent > 0:
            email_logger.info(f"Письмо успешно отправлено на {email}")
            return {"success": f"Письмо отправлено на {email}"}
        else:
            email_logger.warning(f"Письмо не отправлено на {email}")
            raise Exception("Неизвестная ошибка отправки")

    except Exception as exc:
        email_logger.error(f"Ошибка отправки email на {email}: {exc}")
        self.retry(exc=exc, countdown=60 * (self.request.retries + 1))

def create_periodic_task():
    from backend.loggers.celery_logger import logger as celery_logger
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
                celery_logger.info(
                    "🔄 Периодическая задача 'Удаление истёкших токенов' обновлена."
                )
            else:
                celery_logger.info(
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
            celery_logger.info("✅ Периодическая задача 'Удаление истёкших токенов' создана.")

        return task

    except Exception as e:
        celery_logger.error(f"❌ Ошибка при создании периодической задачи: {e}")
        return None
