from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from celery import shared_task
from django.core.mail import send_mail as django_send_mail
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from DiplomNetologyGjango import settings
from backend.loggers.celery_logger import logger as celery_logger
from backend.loggers.jwt_token_logger import logger as jwt_logger
from backend.loggers.mail_send_logger import logger as email_logger
from backend.models import (Category, Parameter, Product, ProductInfo, ProductParameter, Shop, UNITS_OF_MEASURE)

UNIT_CHOICES = {choice[0] for choice in UNITS_OF_MEASURE}


# === ПЕРИОДИЧЕСКИЕ ЗАДАЧИ ===

@shared_task
def delete_expired_tokens():
    """Удаление токенов, просроченных более 2 дней."""
    threshold = timezone.now() - timedelta(days=2)
    count, _ = OutstandingToken.objects.filter(expires_at__lt=threshold).delete()
    jwt_logger.info(f"✅ Удалено {count} истёкших токенов")


# === ОТПРАВКА ПОЧТЫ ===

@shared_task(bind=True, max_retries=3)
def send_email_confirmation(self, email: str, subject: str, message: str, from_email=None):
    """Асинхронная отправка email с повторными попытками."""
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
            email_logger.info(f"✉️ Письмо успешно отправлено на {email}")
            return {"success": f"Письмо отправлено на {email}"}
        raise Exception("Почта не отправлена (неизвестная ошибка)")

    except Exception as exc:
        email_logger.error(f"❌ Ошибка отправки email на {email}: {exc}")
        self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


# === ОБРАБОТКА ДАННЫХ МАГАЗИНА (YAML) ===

@shared_task(bind=True, max_retries=3)
def process_shop_data_async(self, data: dict, user_id: int):
    """Асинхронная обработка YAML-данных магазина."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    celery_logger.info(f"📦 Обработка данных магазина для пользователя ID={user_id}")

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        celery_logger.error(f"❌ Пользователь ID={user_id} не найден.")
        return {"status": False, "errors": ["Пользователь не найден"]}

    return _process_shop_data(data, user)


def _process_shop_data(data: dict, user) -> dict:
    """Внутренняя логика обработки данных магазина."""
    shop_name = data.get("shop")
    if not shop_name:
        return {"status": False, "errors": ["Не указано имя магазина в файле"]}

    shop = _get_or_create_shop(shop_name, user)
    if not shop:
        return {"status": False, "errors": [f"Не удалось создать магазин '{shop_name}'"]}

    category_map = _process_categories(data.get("categories", []), shop)
    result = _process_products(data.get("goods", []), shop, category_map)

    if result["errors"]:
        celery_logger.warning(f"⚠️ Найдены ошибки при обработке: {result['errors']}")

    total = result["created"] + result["updated"]
    celery_logger.info(f"✅ Обработано {total} товаров для магазина '{shop.name}'")
    return result


def _get_or_create_shop(name: str, user) -> Shop | None:
    """Получает или создаёт магазин по имени или slug."""
    from django.utils.text import slugify

    try:
        return Shop.objects.get(name=name, user=user)
    except Shop.DoesNotExist:
        try:
            return Shop.objects.get(slug=name, user=user)
        except Shop.DoesNotExist:
            slug = slugify(name)
            return Shop.objects.create(
                name=name,
                slug=slug,
                user=user,
                state=True,
            )


def _process_categories(categories: list, shop: Shop) -> dict:
    """Обрабатывает категории и возвращает словарь ID → объект."""
    category_map = {}
    for cat in categories:
        cat_id = cat.get("id")
        cat_name = cat.get("name")
        if not cat_id or not cat_name:
            celery_logger.warning(f"⚠️ Некорректная категория: {cat}")
            continue

        category, created = Category.objects.get_or_create(
            id=cat_id, defaults={"name": cat_name}
        )
        category.shops.add(shop)
        category_map[cat_id] = category
        action = "Создана" if created else "Найдена"
        celery_logger.info(f"{action} категория: {category.name} (ID={cat_id})")

    return category_map


def _process_products(goods: list, shop: Shop, category_map: dict) -> dict:
    """Обрабатывает товары и их параметры."""
    result = {"created": 0, "updated": 0, "errors": []}

    for item in goods:
        _process_single_product(item, shop, category_map, result)

    return result


def _process_single_product(item: dict, shop: Shop, category_map: dict, result: dict):
    """Обработка одного товара."""
    external_id = item.get("id")
    category_id = item.get("category")
    model = item.get("model")
    name = item.get("name")
    price = item.get("price")
    price_rrc = item.get("price_rrc")
    quantity = item.get("quantity")
    parameters = item.get("parameters", {})
    unit_of_measure = item.get("unit_of_measure", "pcs")

    # Проверки
    if unit_of_measure not in UNIT_CHOICES:
        error_msg = f"Недопустимая единица измерения '{unit_of_measure}' для товара {name}"
        celery_logger.warning(error_msg)
        result["errors"].append(error_msg)
        return

    if not all([external_id, category_id, model, name, price, price_rrc, quantity]):
        error_msg = f"Недостающие данные в товаре: {item}"
        celery_logger.warning(error_msg)
        result["errors"].append(error_msg)
        return

    try:
        price = Decimal(str(price))
        price_rrc = Decimal(str(price_rrc))
        quantity = Decimal(str(quantity))
    except Exception as e:
        error_msg = f"Ошибка преобразования чисел в товаре {name}: {e}"
        celery_logger.warning(error_msg)
        result["errors"].append(error_msg)
        return

    if category_id not in category_map:
        error_msg = f"Категория {category_id} не найдена для товара {name}"
        celery_logger.warning(error_msg)
        result["errors"].append(error_msg)
        return

    category = category_map[category_id]
    product, _ = Product.objects.get_or_create(name=name, category=category)

    product_info, created = ProductInfo.objects.update_or_create(
        product=product,
        shop=shop,
        external_id=str(external_id),
        defaults={
            "model": model,
            "price": price,
            "price_rrc": price_rrc,
            "quantity": quantity,
            "unit_of_measure": unit_of_measure,
        },
    )

    action = "Создан" if created else "Обновлён"
    celery_logger.info(f"{action} ProductInfo: {product_info} (ID={product_info.id})")
    result["created" if created else "updated"] += 1

    _process_product_parameters(product_info, parameters)


def _process_product_parameters(product_info: ProductInfo, parameters: dict):
    """Обрабатывает параметры товара."""
    for param_name, param_value in parameters.items():
        param_obj, _ = Parameter.objects.get_or_create(name=param_name)
        ProductParameter.objects.update_or_create(
            product_info=product_info,
            parameter=param_obj,
            defaults={"value": str(param_value)},
        )
        celery_logger.info(f"uParam: {param_name}={param_value}")


# === СОЗДАНИЕ ПЕРИОДИЧЕСКИХ ЗАДАЧ ===

def create_periodic_task():
    """Создаёт или обновляет периодические задачи в базе."""
    try:
        # Ежедневно
        interval_daily, _ = IntervalSchedule.objects.get_or_create(
            every=1, period=IntervalSchedule.DAYS
        )

        # Каждый день в 02:00
        crontab_02_00, _ = CrontabSchedule.objects.get_or_create(
            hour=2, minute=0
        )

        _create_or_update_periodic_task(
            name="Удаление истёкших токенов",
            task="backend.tasks.delete_expired_tokens",
            interval=interval_daily,
        )

        _create_or_update_periodic_task(
            name="Генерация ежедневной статистики",
            task="backend.tasks.generate_daily_statistics",
            crontab=crontab_02_00,
        )

        return True

    except Exception as e:
        celery_logger.error(f"❌ Ошибка при настройке периодических задач: {e}")
        return False


def _create_or_update_periodic_task(
    name: str,
    task: str,
    interval=None,
    crontab=None,
    enabled=True,
    one_off=False,
):
    """Универсальная функция создания/обновления PeriodicTask."""
    defaults = {
        "task": task,
        "enabled": enabled,
        "one_off": one_off,
    }

    if interval:
        defaults["interval"] = interval
    if crontab:
        defaults["crontab"] = crontab

    periodic_task, created = PeriodicTask.objects.get_or_create(
        name=name,
        defaults=defaults,
    )

    if not created:
        updated = False
        for key, value in defaults.items():
            if getattr(periodic_task, key) != value:
                setattr(periodic_task, key, value)
                updated = True

        if updated:
            periodic_task.save()
            action = "🔄 Обновлена" if updated else "✅ Актуальна"
            celery_logger.info(f"{action} задача: '{name}'")
        else:
            celery_logger.info(f"✅ Актуальна: '{name}'")
    else:
        celery_logger.info(f"✅ Создана задача: '{name}'")