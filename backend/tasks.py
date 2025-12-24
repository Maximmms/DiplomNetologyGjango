from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from celery import shared_task
from django.core.mail import send_mail as django_send_mail
from django.utils import timezone
from django_celery_beat.models import IntervalSchedule, PeriodicTask
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from DiplomNetologyGjango import settings
from backend.loggers.celery_logger import logger
from backend.models import (Category, DailySalesReport, Order, Parameter, Product, ProductInfo, ProductParameter, Shop,
                            UNITS_OF_MEASURE)

UNIT_CHOICES = {choice[0] for choice in UNITS_OF_MEASURE}

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


@shared_task(bind=True, max_retries=3)
def process_shop_data_async(self,data, user_id):
    """
    Асинхронная задача обработки данных магазина.

    Загружает или обновляет информацию о магазине, категориях и товарах.
    Поддерживает создание магазина, если он не существует.
    Обработка выполняется асинхронно через Celery.

    Args:
        data (dict): Данные из YAML-файла (shop, categories, goods).
        user_id (int): ID пользователя-партнёра.

    Returns:
        dict: Результат обработки: статус, сообщения, количество созданных/обновлённых записей.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    logger.info(f"Запущена обработка данных для пользователя ID={user_id}")

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error(f"Пользователь с id={user_id} не найден.")
        return {"status": False, "errors": ["Пользователь не найден"]}

    shop_name = data.get("shop")
    if not shop_name:
        logger.warning("В файле не указано имя магазина.")
        return {"status": False, "errors": ["Не указано имя магазина в файле"]}

    logger.info(f"Ищем магазин: '{shop_name}' для пользователя {user.email}")

    try:
        shop = Shop.objects.get(name=shop_name, user=user)
        logger.info(f"Магазин найден по имени: {shop.name}")
    except Shop.DoesNotExist:
        try:
            # Попробуем найти по slug
            shop = Shop.objects.get(slug=shop_name, user=user)
            logger.info(f"Магазин найден по slug: {shop.slug}")
        except Shop.DoesNotExist:
            from django.utils.text import slugify
            slug = slugify(shop_name)
            shop = Shop.objects.create(
                name=shop_name,
                slug=slug,
                user=user,
                state=True,
            )
            logger.info(
                f"Создан новый магазин: {shop.name} (slug={shop.slug}) для пользователя {user.email}"
            )

    errors = []
    created_count = 0
    updated_count = 0

    # Обработка категорий
    category_map = {}
    for cat in data.get("categories", []):
        cat_id = cat.get("id")
        cat_name = cat.get("name")
        if not cat_id or not cat_name:
            logger.warning(f"Некорректная категория: {cat}")
            errors.append(f"Некорректная категория: {cat}")
            continue
        category, created = Category.objects.get_or_create(
            id=cat_id, defaults={"name": cat_name}
        )
        category.shops.add(shop)
        category_map[cat_id] = category
        logger.info(
            f"{'Создана' if created else 'Найдена'} категория: {category.name} (ID={cat_id})"
        )

    # Обработка товаров
    for item in data.get("goods", []):
        logger.info(f"Обработка товара: {item.get('name')} (ID={item.get('id')})")

        external_id = item.get("id")
        category_id = item.get("category")
        model = item.get("model")
        name = item.get("name")
        price = item.get("price")
        price_rrc = item.get("price_rrc")
        quantity = item.get("quantity")
        parameters = item.get("parameters", {})
        unit_of_measure = item.get("unit_of_measure", "pcs")  # по умолчанию

        if unit_of_measure not in UNIT_CHOICES:
            logger.warning(f"Недопустимая единица измерения '{unit_of_measure}' для товара {name}")
            errors.append(
                f"Недопустимая единица измерения '{unit_of_measure}' для товара {name}"
            )
            continue

        required_fields = [
            external_id,
            category_id,
            model,
            name,
            price,
            price_rrc,
            quantity,
        ]
        if not all(required_fields):
            logger.warning(f"Недостающие данные в товаре: {item}")
            errors.append(f"Недостающие данные в товаре: {item}")
            continue

        try:
            price = Decimal(str(price))
            price_rrc = Decimal(str(price_rrc))
            quantity = Decimal(str(quantity))
        except Exception as e:
            logger.warning(f"Ошибка преобразования чисел в товаре {name}: {e}")
            errors.append(f"Ошибка в числовых данных товара: {item}")
            continue

        if category_id not in category_map:
            logger.warning(f"Категория {category_id} не найдена в файле")
            errors.append(f"Категория {category_id} не найдена")
            continue
        category = category_map[category_id]

        product, product_created = Product.objects.get_or_create(name=name, category=category)
        if product_created:
            logger.info(f"Создан продукт: {product.name} (ID={product.id})")

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
        if created:
            logger.info(
                f"Создан ProductInfo: {product_info} (ID={product_info.id})"
            )
            created_count += 1
        else:
            logger.info(f"Обновлён ProductInfo: {product_info} (ID={product_info.id})")
            updated_count += 1

        for param_name, param_value in parameters.items():
            param_obj, param_created = Parameter.objects.get_or_create(
                name=param_name
            )
            if param_created:
                logger.info(f"Создан параметр: {param_name}")

            pp, pp_created = ProductParameter.objects.update_or_create(
                product_info=product_info,
                parameter=param_obj,
                defaults={"value": str(param_value)},
            )
            if pp_created:
                logger.info(
                    f"Создан параметр товара: {param_name}={param_value}"
                )

    if errors:
        logger.warning(f"Ошибки при обработке файла: {errors}")
        return {"status": False, "errors": errors}

    logger.info(
        f"Успешно обработано {created_count + updated_count} товаров для магазина {shop.name}"
    )
    return {
        "status": True,
        "message": f"Обработано {created_count + updated_count} товаров",
        "created": created_count,
        "updated": updated_count,
    }

@shared_task
def generate_daily_statistics():
    yesterday = timezone.now().date() - timezone.timedelta(days=1)
    shops = Shop.objects.all()

    for shop in shops:
        completed_orders = Order.objects.filter(shop=shop, created_at__date=yesterday, status='completed')
        total_sales = sum(item.price * item.quantity for order in completed_orders for item in order.items.all())
        order_count = completed_orders.count()

        # Сохраняем отчет
        DailySalesReport.objects.update_or_create(
            shop=shop,
            date=yesterday,
            defaults={
                'total_sales': total_sales,
                'order_count': order_count,
            }
        )

        # Проверка остатков
        low_stock = Product.objects.filter(shop=shop, stock__lt=10)
        if low_stock.exists():
            # Можно отправить уведомление (email, в интерфейс и т.д.)
            print(f"Низкий остаток на складе у магазина {shop.name}: {[p.name for p in low_stock]}")