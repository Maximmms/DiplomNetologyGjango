from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# === ОСНОВНЫЕ ПУТИ И КОНФИГУРАЦИЯ ПРОЕКТА ===
BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = "/logs"  # Папка для логов (должна существовать при запуске)


# === РЕЖИМ РАЗРАБОТКИ И БЕЗОПАСНОСТЬ ===
DEBUG = True
SECRET_KEY = "django-insecure-m+4$%&0tbnpk02%7d!9_4r5i2hy)^xhxghp4sx7p)_^kmlcg*4"
ALLOWED_HOSTS = ["*"]


# === ПРИЛОЖЕНИЯ И MIDDLEWARE ===
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_rest_passwordreset",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "django_celery_beat",
    "backend",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "DiplomNetologyGjango.urls"
WSGI_APPLICATION = "DiplomNetologyGjango.wsgi.application"


# === ПОЛЬЗОВАТЕЛИ И АУТЕНТИФИКАЦИЯ ===
AUTH_USER_MODEL = "backend.User"
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

# Настройки JWT (SimpleJWT)
SIMPLE_JWT = {
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=2),
}


# === БАЗА ДАННЫХ ===
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST"),
        "PORT": os.getenv("DB_PORT"),
        "OPTIONS": {
            "client_encoding": "utf8",
        },
        "ATOMIC_REQUESTS": True,
    }
}


# === ШАБЛОННЫЕ ДВИЖКИ И СТАТИЧЕСКИЕ ФАЙЛЫ ===
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
STATICFILES_DIRS = []


# === ВАЛИДАЦИЯ ПАРОЛЕЙ ===
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# === ЛОКАЛИЗАЦИЯ И ВРЕМЯ ===
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# === EMAIL НАСТРОЙКИ (SMTP) ===
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@example.com")
EMAIL_HOST = os.getenv("EMAIL_HOST", "mailhog")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 1025))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "False").lower() == "true"


# === REST FRAMEWORK (DRF) ===
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 40,
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "backend.utils.exception_handler.custom_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "email_send": "3/hour",
        "login": "5/minute",
        "resend_code": "3/hour",
    },
}


# === ЛОГИРОВАНИЕ ===
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
        "file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": os.path.join(LOGS_DIR, "django.log"),
            "formatter": "standard",
        },
        "jwt_tokens_file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": os.path.join(LOGS_DIR, "jwt_tokens.log"),
            "formatter": "standard",
        },
        "send_email_file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": os.path.join(LOGS_DIR, "send_email.log"),
            "formatter": "standard",
        },
        "celery_file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": os.path.join(LOGS_DIR, "celery.log"),
            "formatter": "standard",
        },
    },
    "loggers": {
        "celery": {
            "handlers": ["console", "celery_file"],
            "level": "INFO",
            "propagate": True,
        },
        "email_sending": {
            "handlers": ["console", "send_email_file"],
            "level": "INFO",
            "propagate": True,
        },
        "backend": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "jwt_tokens": {
            "handlers": ["console", "jwt_tokens_file"],
            "level": "INFO",
            "propagate": True,
        },
    },
}


# === CELERY НАСТРОЙКИ ===
CELERY_BROKER_URL = "redis://redis:6379/0"
CELERY_RESULT_BACKEND = "redis://redis:6379/0"
CELERY_TIMEZONE = "Europe/Moscow"
CELERY_BEAT_SCHEDULE = {}


# === DRF SPECTACULAR (Swagger/OpenAPI) ===
SPECTACULAR_SETTINGS = {
    "TITLE": "Backend API",
    "DESCRIPTION": "API для интернет-магазина: управление пользователями, заказами, магазинами",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "CACHE": None,
    "TAGS": [
        {
            "name": "USER",
            "description": "Работа с пользователями: регистрация, авторизация, профиль, контакты."
        },
        {
            "name": "SHOP",
            "description": "Просмотр магазинов, товаров, категорий и поиск."
        },
        {
            "name": "PARTNERS",
            "description": "API для поставщиков: загрузка прайсов, управление магазином."
        },
        {
            "name": "ORDER",
            "description": "Управление заказами: корзина, оформление, просмотр."
        },
        {
            "name": "BASKET",
            "description": "Работа с корзиной: добавление, удаление, просмотр товаров."
        },
    ],
    "SWAGGER_UI_DIST": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@latest",
    "SWAGGER_UI_FAVICON_32_32": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@latest/favicon-32x32.png",
    "REDOC_DIST": "https://cdn.jsdelivr.net/npm/redoc@next",
    "SCHEMA_PATH_PREFIX": "/api/v1/",
    "CAMELIZE_NAMES": False,
}

# === ДРУГИЕ НАСТРОЙКИ ===
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"