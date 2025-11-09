from __future__ import annotations

import io
from decimal import Decimal

import yaml
from celery import current_app as celery_app
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from backend.loggers.backend_logger import logger
from backend.models import (
    UNITS_OF_MEASURE,
    Category,
    Parameter,
    Product,
    ProductInfo,
    ProductParameter,
    Shop,
)
from backend.utils.permissions import IsShopUser

UNIT_CHOICES = {choice[0] for choice in UNITS_OF_MEASURE}

@celery_app.task(bind=True, max_retries=3)
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
            slug = slugify(shop_name)
            shop = Shop.objects.create(
                name=shop_name,
                slug=slug,
                user=user,
                state=True,
                # другие поля при необходимости
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


@extend_schema(
    summary="Загрузка прайс-листа магазина из YAML-файла",
    description="""
Позволяет партнёрам загружать или обновлять ассортимент товаров через YAML-файл.

### Пример структуры файла:
shop: Связной
categories:
    - id: 224
    name: Смартфоны
goods:
    - id: 4216292
    category: 224
    model: apple/iphone/xs-max
    name: Смартфон Apple iPhone XS Max 512GB
    price: 110000
    price_rrc: 116990
    quantity: 14
    unit_of_measure: pcs
    parameters:
        Диагональ (дюйм): 6.5
        Цвет: золотистый

#### Особенности:
- Только для пользователей с типом `shop`
- Пользователь должен быть владельцем магазина
- Обработка выполняется асинхронно (Celery)
- Поддерживаются `.yaml` и `.yml` файлы
- Можно использовать `name` или `slug` магазина

### Валидация:
- `unit_of_measure` должен быть из допустимого списка
- Обязательные поля: `id`, `category`, `model`, `name`, `price`, `price_rrc`, `quantity`
- Файл не должен быть пустым
    """.strip(),
    request={
        "multipart/form-data": {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "format": "binary",
                    "description": "YAML-файл с прайс-листом",
                }
            },
            "required": ["file"],
        }
    },
    responses={
        202: {
            "type": "object",
            "properties": {
                "status": {"type": "boolean", "example": True},
                "message": {
                    "type": "string",
                    "example": "Файл принят. Обработка началась.",
                },
                "task_id": {
                    "type": "string",
                    "format": "uuid",
                    "example": "c3a5f8b2-1d2e-4f1a-9c1b-2e3d4f5a6b7c",
                },
            },
        },
        400: {
            "type": "object",
            "properties": {
                "status": {"type": "boolean", "example": False},
                "errors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "example": ["Файл не предоставлен"],
                },
            },
        },
        403: {
            "type": "object",
            "properties": {
                "status": {"type": "boolean", "example": False},
                "errors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "example": ["Вы не являетесь владельцем магазина 'Связной'"],
                },
            },
        },
    },
    tags=["PARTNERS"],
    examples=[
        OpenApiExample(
            name="Пример YAML-файла",
            value={
                "shop": "elektronika-24",
                "categories": [{"id": 1, "name": "Смартфоны"}],
                "goods": [
                    {
                        "id": 1001,
                        "category": 1,
                        "model": "iphone-xs",
                        "name": "iPhone XS",
                        "price": 80000,
                        "price_rrc": 85000,
                        "quantity": 5,
                        "unit_of_measure": "pcs",
                        "parameters": {"Цвет": "серебристый"},
                    }
                ],
            },
            description="Пример структуры файла для загрузки",
            request_only=False,
            response_only=False,
        )
    ],
)
@method_decorator(never_cache, name="dispatch")
class PartnerPriceUploadView(APIView):
    """
    Загрузка YAML-файла с товарами магазина.

    Поддерживает:
    - Загрузку по имени или slug магазина
    - Поле `unit_of_measure` в товарах
    - Асинхронную обработку через Celery

    Доступ: только авторизованные пользователи с типом `shop`.
    """
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [IsAuthenticated, IsShopUser]

    def post(self, request, *args, **kwargs):
        """
        Обрабатывает POST-запрос с YAML-файлом.
        Проверяет формат, парсит содержимое и отправляет задачу в Celery.

        Returns:
            JsonResponse: Статус, сообщение и ID задачи.
        """
        file_obj = request.FILES.get("file")

        if not file_obj:
            return JsonResponse(
                {"status": False, "errors": "Файл не предоставлен"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not file_obj.name.endswith((".yaml", ".yml")):
            return JsonResponse(
                {
                    "status": False,
                    "errors": "Поддерживаются только .yaml или .yml файлы",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            data = yaml.safe_load(io.TextIOWrapper(file_obj, encoding="utf-8").read())
        except Exception as e:
            logger.error(f"Ошибка парсинга YAML: {str(e)}")
            return JsonResponse({
                "status": False,
                "errors": f"Ошибка парсинга YAML: {str(e)}"
            }, status=status.HTTP_400_BAD_REQUEST)

        task = process_shop_data_async.delay(data, request.user.id)

        return JsonResponse({
            "status": True,
            "message": "Файл принят. Обработка началась.",
            "task_id": task.id
        }, status=status.HTTP_202_ACCEPTED)