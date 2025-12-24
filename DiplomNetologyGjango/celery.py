from __future__ import annotations

import logging
import os

from celery.schedules import crontab

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "DiplomNetologyGjango.settings")

app = Celery("DiplomNetologyGjango")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Настраиваем логирование для Celery
logger = logging.getLogger("celery")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
    ch.setFormatter(formatter)
    logger.addHandler(ch)

# Расписание задач через Celery Beat
app.conf.beat_schedule = {
    'generate-daily-statistics': {
        'task': 'backend.tasks.generate_daily_statistics',
        'schedule': crontab(hour=2, minute=0),  # Каждый день в 02:00
    },
}