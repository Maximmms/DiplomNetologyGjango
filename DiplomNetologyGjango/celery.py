import os
from celery import Celery
from django.conf import settings
import logging

os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'DiplomNetologyGjango.settings'
)

app = Celery('DiplomNetologyGjango')
app.config_from_object(
    'django.conf:settings',
    namespace='CELERY'
)
app.autodiscover_tasks()

# Настраиваем логирование для Celery
logger = logging.getLogger('celery')
if not logger.handlers:
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)