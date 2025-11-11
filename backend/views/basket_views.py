from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from drf_spectacular.utils import (
    OpenApiExample,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.loggers.backend_logger import logger
from backend.models import Order, OrderItem
from backend.serializers import BasketItemAddSerializer, BasketItemSerializer


@extend_schema(
    summary="Добавить товар(ы) в корзину",
    description="""
Добавляет один или несколько товаров в корзину пользователя.

#### Формат запроса:
- Можно передать **один объект** или **список объектов**
- Каждый объект содержит:
    - `product_info_id` — ID товара (ProductInfo)
    - `quantity` — количество

#### Особенности:
- Все операции в одной транзакции
- Если хотя бы один товар недоступен — ни один не добавляется
- Обновляет количество, если товар уже в корзине
- Проверяет наличие на складе
- Доступ только авторизованным пользователям

#### Примеры тела запроса:
- json [ { "product_info_id": 1, "quantity": 2 }, { "product_info_id": 3, "quantity": 1 } ]
- json { "product_info_id": 1, "quantity": 2 }
    """.strip(),
    tags=["BASKET"],
    request=BasketItemAddSerializer(many=True),
    responses={
        200: inline_serializer(
            name="BasketAddMultipleResponse",
            fields={
                "status": serializers.CharField(help_text="Сообщение об успешном добавлении"),
                "added": serializers.IntegerField(help_text="Количество добавленных позиций"),
                "items": inline_serializer(
                    name="BasketItemAddedResponse",
                    fields=BasketItemSerializer().get_fields(),
                    many=True,
                    help_text="Список добавленных или обновлённых товаров в корзине",
                ),
            },
            help_text="Результат добавления товаров в корзину",
        ),
    },
    examples=[
        OpenApiExample(
            "Пример ответа при добавлении одного товара",
            value={
                "status": "Добавлено товаров: 1",
                "added": 1,
                "items": [
                    {
                        "id": 5,
                        "product_info": {
                            "id": 1,
                            "model": "iphone-15",
                            "price": "99990.00",
                            "price_rrc": "104990.00",
                            "quantity": "2.00",
                            "shop": {
                                "id": 1,
                                "name": "Электроника 24"
                            }
                        },
                        "quantity": "2.00"
                    }
                ]
            },
            response_only=True,
        ),
        OpenApiExample(
            "Пример ответа при добавлении нескольких товаров",
            value={
                "status": "Добавлено товаров: 2",
                "added": 2,
                "items": [
                    {
                        "id": 5,
                        "product_info": {
                            "id": 1,
                            "model": "iphone-15",
                            "price": "99990.00",
                            "shop": {"id": 1, "name": "Электроника 24"}
                        },
                        "quantity": "2.00"
                    },
                    {
                        "id": 6,
                        "product_info": {
                            "id": 3,
                            "model": "galaxy-buds",
                            "price": "12990.00",
                            "shop": {"id": 2, "name": "ТехноМир"}
                        },
                        "quantity": "1.00"
                    }
                ]
            },
            response_only=True,
        ),
    ],
    operation_id="basket_add_items",
)
class BasketAddView(APIView):
    """
    Добавление одного или нескольких товаров в корзину.
    Все операции выполняются в одной транзакции.
    Доступ: только авторизованные пользователи.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Определяем, передан ли один объект или список
        data = request.data
        if isinstance(data, list):
            items_data = data
        else:
            items_data = [data]

        serializer = BasketItemAddSerializer(data=items_data, many=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                basket, created = Order.objects.get_or_create(
                    user=request.user, status="basket", defaults={"contact": None}
                )

                added_count = 0
                order_items = []

                for item in serializer.validated_data:
                    product_info = item["product_info"]
                    quantity = item["quantity"]

                    if product_info.quantity < quantity:
                        raise ValidationError(
                            f"Недостаточно товара '{product_info.product.name}' в наличии: "
                            f"запрошено {quantity}, доступно {product_info.quantity}"
                        )

                    order_item, _ = OrderItem.objects.update_or_create(
                        order=basket,
                        product_info=product_info,
                        defaults={"quantity": quantity},
                    )
                    order_items.append(order_item)
                    added_count += 1

                logger.info(
                    f"Пользователь {request.user.email} добавил {added_count} товар(ов) в корзину"
                )

                return Response(
                    {
                        "status": f"Добавлено товаров: {added_count}",
                        "added": added_count,
                        "items": BasketItemSerializer(order_items, many=True).data,
                    },
                    status=status.HTTP_200_OK,
                )

        except ValidationError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(f"Ошибка при добавлении товаров в корзину: {e}")
            return Response(
                {"error": "Внутренняя ошибка сервера"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema_view(
    delete=extend_schema(
        summary="Удалить товар из корзины",
        description="""
Удаляет один или несколько товаров из корзины пользователя.

#### Формат запроса:
- Можно передать **один объект** с `id` позиции в корзине
- Или **список объектов** с `id`
- `id` — это ID объекта `OrderItem` (позиции в корзине)

#### Особенности:
- Удаляет только позиции из заказа со статусом `basket`
- Пользователь может удалять только свои товары
- Если передан несуществующий `id` — возвращается ошибка
- Все операции в одной транзакции

#### Пример тела запроса:
- json { "id": 5 }
- json [ { "id": 5 }, { "id": 6 } ]
        """.strip(),
        tags=["BASKET"],
        request=inline_serializer(
            name="BasketItemDeleteRequest",
            fields={
                "id": serializers.IntegerField()
            },
            many=True
        ),
        responses={
            200: {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "example": "Удалено 2 позиции из корзины"},
                    "deleted": {"type": "integer", "example": 2}
                }
            },
            400: {
                "type": "object",
                "properties": {
                    "error": {"type": "string"},
                    "invalid_ids": {"type": "array", "items": {"type": "integer"}}
                }
            },
            404: {
                "type": "object",
                "properties": {
                    "error": {"type": "string", "example": "Позиция корзины не найдена"}
                }
            }
        },
        examples=[
            OpenApiExample(
                "Удаление одного товара",
                value={"id": 5},
                request_only=True,
            ),
            OpenApiExample(
                "Удаление нескольких товаров",
                value=[
                    {"id": 5},
                    {"id": 6}
                ],
                request_only=True,
            ),
            OpenApiExample(
                "Пример успешного ответа",
                value={
                    "status": "Удалено 2 позиции из корзины",
                    "deleted": 2
                },
                response_only=True,
            ),
        ],
        operation_id="basket_delete_items",
    )
)
class BasketRemoveView(APIView):
    """
    Удаление одного или нескольких товаров из корзины.
    Все операции выполняются в одной транзакции.
    Доступ: только авторизованные пользователи.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        """
        Обрабатывает удаление позиций из корзины.
        """
        data = request.data
        if isinstance(data, list):
            items_data = data
        else:
            items_data = [data]

        # Валидация: все id — целые числа
        item_ids = []
        for item in items_data:
            if not isinstance(item, dict) or "id" not in item:
                return Response(
                    {"error": "Каждый элемент должен содержать поле 'id'"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            try:
                item_ids.append(int(item["id"]))
            except (ValueError, TypeError):
                return Response(
                    {"error": "Поле 'id' должно быть числом"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if not item_ids:
            return Response(
                {"error": "Не передано ни одного ID"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                # Получаем корзину
                basket = Order.objects.filter(
                    user=request.user,
                    status="basket"
                ).first()

                if not basket:
                    return Response(
                        {"error": "Корзина пуста или не существует"},
                        status=status.HTTP_404_NOT_FOUND
                    )

                # Получаем позиции корзины
                order_items = OrderItem.objects.filter(
                    id__in=item_ids,
                    order=basket
                )

                if len(order_items) != len(item_ids):
                    found_ids = set(order_items.values_list("id", flat=True))
                    not_found = [item_id for item_id in item_ids if item_id not in found_ids]
                    return Response(
                        {
                            "error": "Некоторые позиции не найдены или не принадлежат корзине",
                            "invalid_ids": not_found
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )

                deleted_count, _ = order_items.delete()

                logger.info(
                    f"Пользователь {request.user.email} удалил {deleted_count} позиций из корзины"
                )

                return Response(
                    {
                        "status": f"Удалено {deleted_count} позиций из корзины",
                        "deleted": deleted_count
                    },
                    status=status.HTTP_200_OK
                )

        except Exception as e:
            logger.error(f"Ошибка при удалении товаров из корзины: {e}")
            return Response(
                {"error": "Внутренняя ошибка сервера"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema_view(
    get=extend_schema(
        summary="Получить содержимое корзины",
        description="""
Возвращает список всех товаров в корзине пользователя.

#### Особенности:
- Корзина — это заказ со статусом `basket`
- В ответе указаны:
    - товар
    - магазин
    - цена
    - количество
    - общая сумма корзины
- Если корзина пуста — возвращается пустой список
- Доступ только авторизованным пользователям
        """.strip(),
        tags=["BASKET"],
        responses={
            200: inline_serializer(
                name="BasketGetResponse",
                fields={
                    "total_amount": serializers.DecimalField(
                        max_digits=10,
                        decimal_places=2,
                        help_text="Общая сумма всех товаров в корзине"
                    ),
                    "items": inline_serializer(
                        name="BasketItemGetResponse",
                        fields=BasketItemSerializer().get_fields(),
                        many=True,
                        help_text="Список позиций в корзине"
                    ),
                },
                help_text="Содержимое корзины пользователя",
            ),
        },
        examples=[
            OpenApiExample(
                "Корзина с товарами",
                value={
                    "total_amount": "125000.00",
                    "items": [
                        {
                            "id": 5,
                            "product_info": {
                                "id": 1,
                                "model": "iphone-15",
                                "price": "99990.00",
                                "shop": {"id": 1, "name": "Электроника 24"}
                            },
                            "quantity": "2.00"
                        },
                        {
                            "id": 6,
                            "product_info": {
                                "id": 3,
                                "model": "galaxy-buds",
                                "price": "12990.00",
                                "shop": {"id": 2, "name": "ТехноМир"}
                            },
                            "quantity": "1.00"
                        }
                    ]
                },
                response_only=True,
            ),
            OpenApiExample(
                "Пустая корзина",
                value={
                    "total_amount": "0.00",
                    "items": []
                },
                response_only=True,
            ),
        ],
        operation_id="basket_get",
    )
)
class BasketView(APIView):
    """
    Получение содержимого корзины пользователя.
    Возвращает список товаров и общую сумму.
    Доступ: только авторизованные пользователи.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = BasketItemSerializer

    def get(self, request):
        """
        Возвращает содержимое корзины: товары и общую сумму.
        """
        basket = Order.objects.filter(
            user=request.user,
            status="basket"
        ).prefetch_related(
            "ordered_items__product_info__shop",
            "ordered_items__product_info__product"
        ).first()

        if not basket:
            logger.info(f"Корзина пользователя {request.user.email} не найдена")
            return Response({
                "total_amount": "0.00",
                "items": []
            }, status=status.HTTP_200_OK)

        items = basket.ordered_items.all()
        serializer = self.serializer_class(items, many=True)

        # Вычисляем общую сумму
        total_amount = sum(
            item.product_info.price * item.quantity for item in items
        )

        logger.info(
            f"Пользователь {request.user.email} запросил содержимое корзины: {len(items)} позиций"
        )

        return Response({
            "total_amount": f"{total_amount:.2f}",
            "items": serializer.data
        }, status=status.HTTP_200_OK)
