from __future__ import annotations

import io

import yaml
from django.db import transaction
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.utils import timezone
from rest_framework.views import APIView

from backend.loggers.backend_logger import logger
from backend.models import (
    Order,
    OrderHistory, Shop,
)
from backend.serializers import OrderSerializer
from backend.tasks import process_shop_data_async, send_email_confirmation
from backend.utils.permissions import IsShopUser


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
        ),
        OpenApiExample(
            name="Успешная загрузка",
            summary="Пример ответа при успешной отправке файла",
            value={
                "status": True,
                "message": "Файл принят. Обработка началась.",
                "task_id": "c3a5f8b2-1d2e-4f1a-9c1b-2e3d4f5a6b7c",
            },
            response_only=True,
        ),
        OpenApiExample(
            name="Ошибка валидации",
            summary="Пример ответа при ошибке",
            value={
                "status": False,
                "errors": ["Поддерживаются только .yaml или .yml файлы"],
            },
            response_only=True,
        ),
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


@extend_schema_view(
    get=extend_schema(
        summary="Получить статус магазина",
        description="Возвращает текущий статус магазина: активен или нет.",
        tags=["PARTNERS"],
        responses={
            200: {
                "type": "object",
                "properties": {
                    "state": {"type": "boolean", "example": True},
                    "shop_name": {"type": "string", "example": "Электроника 24"}
                }
            },
            404: {
                "type": "object",
                "properties": {
                    "error": {"type": "string", "example": "Магазин не найден."}
                }
            }
        },
        examples=[
            OpenApiExample(
                name="Текущий статус магазина",
                summary="Пример ответа с активным статусом",
                value={
                    "state": True,
                    "shop_name": "Электроника-24"
                },
                response_only=True,
            ),
            OpenApiExample(
                name="Магазин не найден",
                summary="Пример ответа при отсутствии магазина",
                value={"error": "Магазин не найден."},
                response_only=True,
            ),
        ],
        operation_id="partner_shop_state_get",
    ),
    post=extend_schema(
        summary="Изменить статус магазина",
        description="""
Изменяет статус магазина (принимает заказы / не принимает заказы).
- Доступно только авторизованным пользователям с типом `shop`.
- Пользователь должен быть владельцем магазина.
- Принимает `true` или `false` в теле запроса.
        """.strip(),
        tags=["PARTNERS"],
        request=inline_serializer(
            name="ChangeShopState",
            fields={"state": serializers.BooleanField()}
        ),
        responses={
            200: {
                "type": "object",
                "properties": {
                    "state": {"type": "boolean", "example": True},
                    "message": {"type": "string", "example": "Статус магазина обновлён."}
                }
            },
            400: {
                "type": "object",
                "properties": {
                    "error": {"type": "string"}
                }
            },
            403: {
                "type": "object",
                "properties": {
                    "error": {"type": "string"}
                }
            },
            404: {
                "type": "object",
                "properties": {
                    "error": {"type": "string"}
                }
            }
        },
        examples=[
            OpenApiExample(
                name="Изменение статуса",
                summary="Пример запроса на активацию магазина",
                value={"state": True},
                request_only=True,
            ),
            OpenApiExample(
                name="Успешное обновление",
                summary="Пример успешного ответа",
                value={
                    "state": True,
                    "message": "Статус магазина обновлён."
                },
                response_only=True,
            ),
            OpenApiExample(
                name="Ошибка ввода",
                summary="Пример ошибки при неверном формате",
                value={"error": "Поле 'state' должно быть true или false."},
                response_only=True,
            ),
        ],
        operation_id="partner_shop_state_post",
    )
)
class PartnerShopStateView(APIView):
    """
    Получение и изменение статуса магазина (активен / неактивен).
    Доступ: только владелец магазина (пользователь с type='shop').
    """
    permission_classes = [IsAuthenticated, IsShopUser]

    def get(self, request):
        """
        Возвращает текущий статус магазина.
        """
        try:
            shop = Shop.objects.get(user=request.user)
            return Response({
                "state": shop.state,
                "shop_name": shop.name
            }, status=status.HTTP_200_OK)
        except Shop.DoesNotExist:
            return Response(
                {"error": "Магазин не найден."},
                status=status.HTTP_404_NOT_FOUND
            )

    def post(self, request):
        """
        Обновляет статус магазина.
        Принимает `state: true/false`.
        """
        state_raw = request.data.get("state")

        if state_raw is None:
            return Response(
                {"error": "Требуется поле 'state' (true или false)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            state = bool(state_raw)
        except (ValueError, TypeError):
            return Response(
                {"error": "Поле 'state' должно быть true или false."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            shop = Shop.objects.get(user=request.user)
        except Shop.DoesNotExist:
            return Response(
                {"error": "Магазин не найден."},
                status=status.HTTP_404_NOT_FOUND
            )

        shop.state = state
        shop.save()

        action = "активирован" if state else "деактивирован"
        logger.info(f"Магазин {shop.name} {action} пользователем {request.user.email}")

        return Response({
            "state": shop.state,
            "message": "Статус магазина обновлён."
        }, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        summary="Получить заказы для магазина",
        description="""
Возвращает список заказов, содержащих товары из текущего магазина.
Поддерживает фильтрацию по статусу и дате.
        """.strip(),
        tags=["PARTNERS"],
        parameters=[
            OpenApiParameter(
                name="status",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Фильтр по статусу заказа",
                enum=["new", "confirmed", "assembled", "sent", "delivered", "canceled"],
                required=False,
            ),
            OpenApiParameter(
                name="date_from",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="Фильтр: дата от (YYYY-MM-DD)",
                required=False,
            ),
            OpenApiParameter(
                name="date_to",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="Фильтр: дата до (YYYY-MM-DD)",
                required=False,
            ),
        ],
        responses={
            200: {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "integer"},
                        "status": {"type": "string"},
                        "created_at": {"type": "string", "format": "date-time"},
                        "user": {"type": "object", "properties": {"email": {"type": "string"}}},
                        "contact": {"type": "string"},
                        "items": {"type": "array", "items": {"type": "object"}},
                        "total_amount": {"type": "number"},
                    },
                },
            }
        },
        examples=[
            OpenApiExample(
                name="Список заказов",
                summary="Пример ответа с двумя заказами",
                value=[
                    {
                        "order_id": 1,
                        "status": "confirmed",
                        "created_at": "2024-04-05T10:00:00Z",
                        "user": {
                            "email": "buyer@example.com",
                            "first_name": "Иван",
                            "last_name": "Иванов"
                        },
                        "contact": "+79991234567",
                        "items": [
                            {
                                "product": "iPhone 15",
                                "model": "Apple iPhone 15",
                                "quantity": 1.0,
                                "unit_of_measure": "шт",
                                "price": 100000.0,
                                "total": 100000.0
                            }
                        ],
                        "total_amount": 100000.0
                    }
                ],
                response_only=True,
            ),
            OpenApiExample(
                name="Пример запроса с фильтром",
                summary="GET /api/partners/orders/?status=confirmed&date_from=2024-04-01",
                description="Пример вызова с query-параметрами",
                value=None,
                request_only=True,
            ),
        ],
        operation_id="partner_orders",
    )
)
class PartnerOrdersView(APIView):
    """
    Получение заказов, содержащих товары магазина.
    Доступ: только авторизованные пользователи с типом `shop`.
    """
    permission_classes = [IsAuthenticated, IsShopUser]

    def get(self, request):
        try:
            shop = Shop.objects.get(user=request.user)
        except Shop.DoesNotExist:
            return Response(
                {"error": "Магазин не найден."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Начинаем с заказов, содержащих товары из этого магазина
        queryset = Order.objects.filter(
            ordered_items__product_info__shop=shop
        ).distinct().select_related("user", "contact").prefetch_related(
            "ordered_items__product_info__product",
            "ordered_items__product_info"
        ).order_by("-created_at")

        # Фильтрация по статусу
        status_filter = request.query_params.get("status")
        if status_filter:
            if status_filter not in dict(Order.ORDER_STATUS_CHOICES):
                return Response(
                    {"error": "Некорректный статус."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(status=status_filter)

        # Фильтрация по дате
        date_from = request.query_params.get("date_from")
        if date_from:
            try:
                date_from = timezone.datetime.strptime(date_from, "%Y-%m-%d").date()
                queryset = queryset.filter(created_at__date__gte=date_from)
            except ValueError:
                return Response(
                    {"error": "Некорректный формат даты 'date_from'. Используйте YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        date_to = request.query_params.get("date_to")
        if date_to:
            try:
                date_to = timezone.datetime.strptime(date_to, "%Y-%m-%d").date()
                queryset = queryset.filter(created_at__date__lte=date_to)
            except ValueError:
                return Response(
                    {"error": "Некорректный формат даты 'date_to'. Используйте YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        orders_data = []
        for order in queryset:
            items = order.ordered_items.filter(product_info__shop=shop)
            shop_items_data = []
            total_amount = 0

            for item in items:
                price = item.product_info.price
                quantity = item.quantity
                item_total = price * quantity
                total_amount += item_total

                shop_items_data.append({
                    "product": item.product_info.product.name,
                    "model": item.product_info.model,
                    "quantity": float(quantity),
                    "unit_of_measure": item.product_info.get_unit_of_measure_display(),
                    "price": float(price),
                    "total": float(item_total),
                })

            orders_data.append({
                "order_id": order.id,
                "status": order.status,
                "created_at": order.created_at,
                "user": {
                    "email": order.user.email,
                    "first_name": order.user.first_name,
                    "last_name": order.user.last_name,
                },
                "contact": str(order.contact) if order.contact else "-",
                "items": shop_items_data,
                "total_amount": float(total_amount),
            })

        return Response(orders_data, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
        summary="Подтвердить сборку своей части заказа",
        description = """
        Позволяет магазину подтвердить, что он готов собрать свои товары из заказа.
        Если какого-то товара нет у поставщика, он может быть удалён из заказа с уведомлением клиента.
                """.strip(),
        tags=["PARTNERS"],
        request = {
            "application/json":{
                "type":"object",
                "properties":{
                    "order_id":{
                        "type":"integer",
                        "example":1,
                        "description":"ID заказа"
                    },
                    "rejected_items":{
                        "type":"array",
                        "items":{"type":"integer"},
                        "description":"Список ID позиций (ordered_item_id), которые нельзя поставить",
                        "example":[1, 3],
                        "required":False,
                    }
                },
                "required":["order_id"]
            }
        },
        responses={200: OrderSerializer, 400: {"type": "object"}, 404: {"type": "object"}},
        examples = [
            OpenApiExample(
                name = "Подтверждение с отказом по позициям",
                summary = "Магазин подтверждает часть заказа, но отменяет некоторые позиции",
                value = {"order_id":1, "rejected_items":[5]},
                request_only = True,
            ),
            OpenApiExample(
                name = "Успех",
                summary = "Пример успешного ответа",
                value = {
                    "id":1,
                    "status":"assembled",
                    "created_at":"2024-04-05T10:00:00Z",
                    "user":1,
                    "contact":1,
                    "ordered_items":[
                        {
                            "id":1,
                            "order":1,
                            "product_info":1,
                            "quantity":"1.00",
                            "shop_confirmed":True
                        }
                    ]
                },
                response_only = True,
            ),
        ],
        operation_id="partner_order_confirm",
    )
)
class PartnerConfirmOrderView(APIView):
    permission_classes = [IsAuthenticated, IsShopUser]

    @transaction.atomic
    def post(self, request):
        order_id = request.data.get("order_id")
        rejected_item_ids = request.data.get("rejected_items", [])

        if not order_id:
            return Response(
                {"status": "error", "errors": "Требуется указать order_id."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            order = Order.objects.select_for_update().get(id=order_id)
        except Order.DoesNotExist:
            return Response(
                {"status": "error", "errors": "Заказ не найден."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            shop = Shop.objects.get(user=request.user)
        except Shop.DoesNotExist:
            return Response(
                {"status": "error", "errors": "Магазин не найден."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if order.status != "confirmed":
            return Response(
                {"status": "error", "errors": f"Заказ должен быть в статусе 'confirmed'. Текущий статус: {order.status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        shop_items = order.ordered_items.filter(product_info__shop=shop).select_related("product_info")
        if not shop_items.exists():
            return Response(
                {"status": "error", "errors": "В этом заказе нет товаров из вашего магазина."},
                status=status.HTTP_403_FORBIDDEN,
            )

        rejected_items = shop_items.filter(id__in=rejected_item_ids)
        confirmed_items = shop_items.exclude(id__in=rejected_item_ids)

        out_of_stock = []
        for item in confirmed_items:
            if item.quantity > item.product_info.quantity:
                out_of_stock.append({
                    "product": item.product_info.product.name,
                    "model": item.product_info.model,
                    "available": item.product_info.quantity,
                    "ordered": item.quantity
                })

        if out_of_stock:
            return Response(
                {
                    "status": "error",
                    "errors": "Недостаточно товара на складе",
                    "details": out_of_stock
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        self._log_action(
            order=order,
            user=request.user,
            action="partner_action",
            details={
                "message":"Поставщик начал подтверждение",
                "confirmed_count":confirmed_items.count(),
                "rejected_count":rejected_items.count(),
                "shop":shop.name
            }
        )

        if rejected_items:
            self._handle_rejected_items(rejected_items, order, request.user)

        for item in confirmed_items:
            product_info = item.product_info
            product_info.quantity -= item.quantity
            product_info.save(update_fields=["quantity"])

            item.shop_confirmed = True
            item.save(update_fields=["shop_confirmed"])

        self._log_action(
            order=order,
            user=request.user,
            action="item_confirmed",
            details={
                "item_id":item.id,
                "product":item.product_info.product.name,
                "model":item.product_info.model,
                "quantity":float(item.quantity),
                "shop":shop.name
            }
        )

        logger.info(f"Магазин '{shop.name}' подтвердил часть заказа #{order_id}, отклонено: {len(rejected_items)} позиций.")
        old_status = order.status

        remaining_items = order.ordered_items.exclude(status="rejected")
        if not remaining_items.exists():
            order.status = "canceled"
            order.save(update_fields = ["status"])
            self._notify_user_order_canceled(order)
            self._log_action(
                order = order,
                user = request.user,
                action = "order_canceled",
                details = {
                    "previous_status":old_status,
                    "reason":"Все товары отменены поставщиками"
                }
            )
        elif all(item.shop_confirmed for item in remaining_items):
            order.status = "assembled"
            order.save(update_fields = ["status"])
            logger.info(f"Заказ #{order_id} переведён в статус 'assembled'.")
            self.send_assembled_confirmation_email(order)
            self._log_action(
                order = order,
                user = request.user,
                action = "order_assembled",
                details = {
                    "previous_status":old_status
                }
            )

        serializer = OrderSerializer(order)
        return Response(serializer.data, status = status.HTTP_200_OK)

    def _handle_rejected_items(self, rejected_items, order, user):
        """Помечает позиции как отменённые поставщиком (не удаляет)."""
        removed_items_info = []
        for item in rejected_items:
            removed_items_info.append({
                "product": item.product_info.product.name,
                "model": item.product_info.model,
                "quantity": float(item.quantity)
            })
            # Удаляем позицию
            item.status = "rejected"
            item.shop_confirmed = False
            item.save(update_fields=["status", "shop_confirmed"])

            self._log_action(
                order = order,
                user = user,
                action = "item_rejected",
                details = {
                    "item_id":item.id,
                    "product":item.product_info.product.name,
                    "model":item.product_info.model,
                    "quantity":float(item.quantity),
                    "shop":item.product_info.shop.name
                }
            )

        # Отправляем email
        self._notify_user_items_removed(order, removed_items_info)

    def _log_action(self, order, user, action, details=None):
        OrderHistory.objects.create(
            order = order,
            action = action,
            details = details,
            user = user
        )

    def _notify_user_items_removed(self, order, removed_items):
        """Отправляет клиенту уведомление об удалении позиций из заказа."""
        if not order.user.email:
            logger.warning(f"Не могу отправить email: у пользователя {order.user.email} не указан email.")
            return

        subject = f"Корректировка заказа #{order.id}"
        message = (
            f"Здравствуйте, {order.user.first_name or 'Уважаемый клиент'}\n\n"
            f"К сожалению, следующие позиции из вашего заказа #{order.id} временно недоступны и были удалены:\n\n"
        )

        for item in removed_items:
            message += f"- {item['product']} ({item['model']}), кол-во: {item['quantity']}\n"

        message += (
            "\nЗаказ будет обработан с оставшимися товарами.\n"
            "Если хотите, вы можете оформить новый заказ на недостающие позиции.\n\n"
            "Спасибо за понимание!\n"
            "С уважением, команда интернет-магазина"
        )

        send_email_confirmation.delay(
            email=order.user.email,
            subject=subject,
            message=message,
            from_email=None
        )

    def _notify_user_order_canceled(self, order):
        """Отправляет клиенту уведомление об отмене заказа из-за отсутствия всех позиций."""
        if not order.user.email:
            logger.warning(f"Не могу отправить email: у пользователя {order.user.email} не указан email.")
            return

        subject = f"Заказ #{order.id} отменён"
        message = (
            f"Здравствуйте, {order.user.first_name or 'Уважаемый клиент'}\n\n"
            f"Ваш заказ #{order.id} был отменён, потому что все товары временно недоступны.\n"
            "Мы приносим свои извинения за доставленные неудобства.\n\n"
            "Вы можете оформить новый заказ, когда товары появятся в наличии.\n\n"
            "С уважением, команда интернет-магазина"
        )

        send_email_confirmation.delay(
            email=order.user.email,
            subject=subject,
            message=message,
            from_email=None
        )

    def send_assembled_confirmation_email(self, order: Order):
        """
        Отправляет клиенту письмо о готовности заказа к отправке.

        Письмо отправляется асинхронно через Celery при переходе заказа в статус 'assembled'.
        Перед отправкой проверяется наличие email у пользователя.
        """
        if not order.user.email:
            logger.warning(
                f"Не могу отправить email: у пользователя {order.user.email} не указан email."
            )
            return

        subject = f"Ваш заказ #{order.id} собран и готов к отправке"
        message = (
            f"Здравствуйте, {order.user.first_name or 'Уважаемый клиент'}\n\n"
            f"Ваш заказ #{order.id} полностью собран и готов к отправке.\n"
            f"Мы сообщим, когда он будет передан в службу доставки.\n\n"
            f"Спасибо за покупку!\n"
            f"С уважением, команда интернет-магазина"
        )

        send_email_confirmation.delay(
            email=order.user.email,
            subject=subject,
            message=message,
            from_email=None
        )