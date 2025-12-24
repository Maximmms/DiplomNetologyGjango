from __future__ import annotations

from django.db import transaction
from django.db.models import Prefetch
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.models import Contact, Order, OrderHistory, OrderItem, Shop
from backend.serializers import OrderHistorySerializer, OrderSerializer
from backend.tasks import send_email_confirmation
from backend.utils.permissions import IsShopUserOrOwner


@extend_schema_view(
    get=extend_schema(
        summary="Получить свои заказы",
        description="""
Возвращает список всех заказов текущего пользователя.

#### Параметры:
- `status` — фильтрация по статусу заказа:
    - `new` — новый
    - `confirmed` — подтверждён
    - `assembled` — собран
    - `sent` — отправлен
    - `delivered` — доставлен
    - `canceled` — отменён

#### Особенности:
- Доступ только авторизованным пользователям
- В заказе отображаются:
    - общий статус
    - общая сумма
    - позиции (товар, магазин, цена, количество)
- Заказы сортируются по дате создания (новые — первыми)
        """.strip(),
        tags=["ORDER"],
        parameters=[
            OpenApiParameter(
                name="status",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Фильтр по статусу заказа",
                enum=[choice[0] for choice in Order.ORDER_STATUS_CHOICES],
                required=False,
            ),
        ],
        responses={200: OrderSerializer(many=True)},
        examples=[
            OpenApiExample(
                name="Список заказов",
                summary="Пример ответа со списком заказов",
                value=[
                    {
                        "id": 2,
                        "status": "new",
                        "created_at": "2024-05-01T10:00:00Z",
                        "total_amount": 100000,
                        "contact": {
                            "id": 1,
                            "city": "Москва",
                            "street": "Ленина",
                            "house": "10",
                            "phone": "+79991234567"
                        },
                        "items": [
                            {
                                "id": 2,
                                "product_info": {
                                    "id": 1,
                                    "name": "iPhone 15",
                                    "model": "Apple iPhone 15 128GB",
                                    "price": 100000,
                                    "shop": {
                                        "id": 1,
                                        "name": "Электроника-24"
                                    }
                                },
                                "quantity": 1,
                                "shop_confirmed": False
                            }
                        ]
                    }
                ],
                response_only=True,
            ),
            OpenApiExample(
                name="Пример запроса с фильтром",
                summary="GET /api/order/?status=confirmed",
                description="Передача параметра status через query string",
                value=None,
                request_only=True,
            ),
        ],
        operation_id="order_list",
    )
)
class UserOrdersView(APIView):
    """
    Получение списка заказов текущего пользователя.
    Поддерживает фильтрацию по статусу.
    Доступ: только авторизованные пользователи.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer

    def get_queryset(self):
        """
        Возвращает queryset заказов пользователя с предзагрузкой товаров и магазинов.
        """
        queryset = (
            Order.objects
            .filter(user=self.request.user)
            .select_related("delivery_address")
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=OrderItem.objects.select_related("product_info__shop", "product_info__product")
                )
            )
            .order_by("-dt")
        )

        status = self.request.query_params.get("status")
        if status:
            if status not in dict(Order.ORDER_STATUS_CHOICES):
                return Order.objects.none()
            queryset = queryset.filter(status=status)

        return queryset

    def get(self, request):
        """
        Возвращает список заказов пользователя с пагинацией.
        """
        queryset = self.get_queryset()
        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
        summary="Создать заказ из корзины",
        description="""
Переводит корзину (status='basket') в статус 'new'.

#### Требования:
- Должна существовать корзина (status='basket') с товарами.
- Пользователь должен быть авторизован.

#### Процесс:
1. Находит заказ со статусом 'basket'.
2. Меняет статус на 'new'.

#### Ответ:
- Возвращает данные заказа в статусе 'new'.
        """.strip(),
        tags=["ORDER"],
        responses={200: OrderSerializer, 400: {"type": "object"}, 404: {"type": "object"}},
        examples=[
            OpenApiExample(
                name="Успешное создание заказа",
                summary="Пример успешного ответа",
                value={
                    "id": 2,
                    "status": "new",
                    "created_at": "2024-05-01T10:00:00Z",
                    "total_amount": 50000,
                    "items": [
                        {
                            "id": 2,
                            "product_info": {
                                "id": 3,
                                "name": "AirPods",
                                "model": "Apple AirPods Pro",
                                "price": 25000,
                                "shop": {
                                    "id": 1,
                                    "name": "Электроника-24"
                                }
                            },
                            "quantity": 2
                        }
                    ]
                },
                response_only=True,
            ),
            OpenApiExample(
                name="Корзина пуста",
                summary="Пример ошибки при пустой корзине",
                value={"status": "error", "errors": "Нельзя создать заказ из пустой корзины."},
                response_only=True,
            ),
        ],
        operation_id="order_create",
    )
)
class CreateOrderFromBasketView(APIView):
    """
    Создаёт новый заказ из корзины.
    Изменяет статус с 'basket' на 'new'.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer

    @transaction.atomic
    def post(self, request):
        order = Order.objects.filter(user=request.user, status="basket").first()
        if not order:
            return Response(
                {"status": "error", "errors": "Корзина пуста или не найдена."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not order.items.exists():
            return Response(
                {"status": "error", "errors": "Нельзя создать заказ из пустой корзины."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.status = "new"
        order.save(update_fields=["status"])

        serializer = self.serializer_class(order)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
        summary="Удалить созданный заказ",
        description="""
Удаляет заказ со статусом 'new'.
Заказ может быть удалён только если его статус 'new' и он принадлежит пользователю.

#### Требования:
- Заказ должен существовать.
- Статус заказа должен быть 'new'.
- Заказ должен принадлежать текущему пользователю.

#### Процесс:
1. Находит заказ по ID.
2. Проверяет статус и принадлежность.
3. Удаляет заказ (полное удаление из БД).

#### Ответ:
- Возвращает статус `ok` при успехе.
        """.strip(),
        tags=["ORDER"],
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer", "example": 1, "description": "ID заказа"}
                },
                "required": ["order_id"]
            }
        },
        responses={
            200: {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "example": "ok"},
                    "message": {"type": "string"}
                }
            },
            400: {"type": "object", "properties": {"status": "string", "errors": "string"}},
            404: {"type": "object", "properties": {"status": "string", "errors": "string"}}
        },
        examples=[
            OpenApiExample(
                name="Успешное удаление",
                summary="Пример запроса на удаление заказа",
                value={"order_id": 2},
                request_only=True,
            ),
            OpenApiExample(
                name="Успешный ответ",
                summary="Пример ответа при успешном удалении",
                value={"status": "ok", "message": "Заказ #2 успешно удалён."},
                response_only=True,
            ),
            OpenApiExample(
                name="Ошибка: статус не 'new'",
                summary="Пример ошибки при попытке удалить подтверждённый заказ",
                value={"status": "error", "errors": "Удалить можно только заказ со статусом 'new'."},
                response_only=True,
            ),
        ],
        operation_id="order_delete",
    )
)
class DeleteOrderView(APIView):
    """
    Удаление заказа со статусом 'new'.
    Пользователь может удалить только свой заказ, если он ещё не размещён.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        order_id = request.data.get("order_id")

        if not order_id:
            return Response(
                {"status": "error", "errors": "Требуется указать order_id."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            order = Order.objects.get(id=order_id, user=request.user)
        except Order.DoesNotExist:
            return Response(
                {"status": "error", "errors": "Заказ не найден."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if order.status != "new":
            return Response(
                {"status": "error", "errors": "Удалить можно только заказ со статусом 'new'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.delete()

        return Response(
            {"status": "ok", "message": f"Заказ #{order_id} успешно удалён."},
            status=status.HTTP_200_OK,
        )


@extend_schema_view(
    post=extend_schema(
        summary="Разместить заказ",
        description="""
Подтверждает и размещает конкретный заказ: переводит заказ из статуса 'new' в 'confirmed'.

#### Требования:
- Указанный заказ должен принадлежать пользователю.
- Статус заказа должен быть 'new'.
- В теле запроса должен быть указан `contact` (ID контактной информации).

#### Процесс:
1. Находит заказ по ID.
2. Проверяет, что статус 'new' и принадлежит пользователю.
3. Проверяет наличие позиций.
4. Назначает контакт.
5. Меняет статус на 'confirmed'.
6. Асинхронно отправляет письмо клиенту о приёмке заказа.
7. Асинхронно отправляет заявки поставщикам (магазинам) на сборку товаров.

#### Ответ:
- Возвращает данные размещённого заказа.
        """.strip(),
        tags=["ORDER"],
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer", "example": 1, "description": "ID заказа"},
                    "contact": {"type": "integer", "example": 1, "description": "ID контактной информации"}
                },
                "required": ["order_id", "contact"]
            }
        },
        responses={200: OrderSerializer, 400: {"type": "object"}, 404: {"type": "object"}},
        examples=[
            OpenApiExample(
                name="Размещение заказа",
                summary="Пример запроса на размещение заказа",
                value={"order_id": 2, "contact": 1},
                request_only=True,
            ),
            OpenApiExample(
                name="Успешное размещение",
                summary="Пример ответа при успешном размещении",
                value={
                    "id": 2,
                    "status": "confirmed",
                    "created_at": "2024-05-01T10:00:00Z",
                    "total_amount": 100000,
                    "delivery_address": {
                        "id": 1,
                        "city": "Москва",
                        "street": "Ленина",
                        "house": "10",
                        "phone": "+79991234567"
                    },
                    "items": [
                        {
                            "id": 2,
                            "product_info": {
                                "id": 1,
                                "name": "iPhone 15",
                                "model": "Apple iPhone 15 128GB",
                                "price": 100000,
                                "shop": {
                                    "id": 1,
                                    "name": "Электроника-24"
                                }
                            },
                            "quantity": 1,
                            "shop_confirmed": False
                        }
                    ]
                },
                response_only=True,
            ),
            OpenApiExample(
                name="Ошибка: контакт не найден",
                summary="Пример ошибки при неверном contact ID",
                value={"status": "error", "errors": "Контакт не найден или недоступен."},
                response_only=True,
            ),
        ],
        operation_id="order_place",
    )
)
class PlaceOrderView(APIView):
    """
    Подтверждение конкретного заказа: перевод из 'new' в 'confirmed'.
    Пользователь указывает order_id и contact.
    После подтверждения:
    - клиент получает письмо о приёмке заказа,
    - поставщики (магазины) получают заявки на сборку.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer

    @transaction.atomic
    def post(self, request):
        order_id = request.data.get("order_id")
        contact_id = request.data.get("contact")

        if not order_id:
            return Response(
                {"status": "error", "errors": "Требуется указать order_id."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not contact_id:
            return Response(
                {"status": "error", "errors": "Требуется указать контакт (contact)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            contact = Contact.objects.get(id=contact_id, user=request.user)
        except Contact.DoesNotExist:
            return Response(
                {"status": "error", "errors": "Контакт не найден или недоступен."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            order = Order.objects.get(id=order_id, user=request.user, status="new")
        except Order.DoesNotExist:
            return Response(
                {
                    "status": "error",
                    "errors": "Заказ не найден или не в статусе 'new'.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if not order.items.exists():
            return Response(
                {"status": "error", "errors": "Нельзя разместить пустой заказ."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        customer_email = request.user.email
        if not customer_email:
            return Response(
                {"status": "error", "errors": "У пользователя не указан email."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.delivery_address = contact
        order.status = "confirmed"
        order.save(update_fields=["delivery_address", "status"])

        self.send_confirmation_email_async(order)

        self.send_supplier_requests_async(order)

        serializer = self.serializer_class(order)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def send_confirmation_email_async(self, order: Order):
        """
        Отправляет клиенту письмо о подтверждении заказа.

        Письмо отправляется асинхронно через Celery после размещения заказа.
        Перед отправкой проверяется наличие email у пользователя.
        """
        recipient_email = order.user.email
        subject = f"Подтверждение заказа #{order.id}"
        message = self.build_email_message(order)

        # Отправляем задачу в Celery
        send_email_confirmation.delay(
            email=recipient_email,
            subject=subject,
            message=message,
            from_email=None
        )

    def build_email_message(self, order: Order) -> str:
        """
        Формирует текст письма для уведомления клиента о подтверждении заказа.

        Включает:
        - Номер заказа
        - Список товаров с количеством и ценой
        - Общую сумму
        - Адрес доставки
        """
        lines = [
            f"Здравствуйте, {order.user.first_name or 'Уважаемый клиент'},\n",
            f"Ваш заказ #{order.id} принят и находится в обработке.\n",
            "Состав заказа:",
        ]

        total_price = 0
        for item in order.items.all():
            price = item.quantity * item.product_info.price
            total_price += price
            lines.append(f" - {item.product_info.product.name}: {item.quantity} шт. × {item.product_info.price} ₽ = {price} ₽")

        lines.append(f"\nОбщая сумма: {total_price} ₽")
        lines.append(f"Адрес доставки: {order.delivery_address}")
        lines.append("\nСпасибо за заказ!")
        lines.append("С уважением, команда вашего интернет-магазина.")

        return "\n".join(lines)

    def send_supplier_requests_async(self, order: Order):
        """
        Отправляет поставщикам (магазинам) письма с заявками на сборку товаров.

        Для каждого магазина, участвующего в заказе, формируется отдельное письмо.
        Отправка выполняется асинхронно через Celery.
        """
        shop_items = {}

        for item in order.items.select_related("product_info__shop"):
            shop = item.product_info.shop
            if shop.user.email:
                if shop not in shop_items:
                    shop_items[shop] = []
                shop_items[shop].append(item)

        for shop, items in shop_items.items():
            subject = f"Заявка на сборку от заказа #{order.id}"
            message = self.build_supplier_message(order, shop, items)
            send_email_confirmation.delay(
                email=shop.user.email,
                subject=subject,
                message=message,
                from_email=None
            )

    def build_supplier_message(self, order: Order, shop: Shop, items) -> str:
        """
        Формирует текст письма для поставщика (магазина) с деталями заявки на сборку.

        Включает:
        - Номер заказа
        - Email клиента
        - Список товаров с количеством и артикулом
        - Адрес доставки
        """
        lines = [
            f"Уважаемый {shop.name},\n",
            f"Поступила заявка на сборку заказа #{order.id} от {order.user.email}.\n",
            "Требуется собрать следующие товары:",
        ]

        for item in items:
            lines.append(
                f" - {item.product_info.product.name}: {item.quantity} шт. (артикул: {item.product_info.external_id})"
            )

        lines.append(f"\nАдрес доставки: {order.delivery_address}")
        lines.append("Прошу подтвердить готовность к сборке в ближайшее время.")
        lines.append("С уважением, команда интернет-магазина.")

        return "\n".join(lines)


@extend_schema(
    summary="Просмотр истории изменений заказа",
    description="""
    Позволяет клиенту или поставщику просматривать историю изменений заказа.
    - Клиент видит историю своего заказа.
    - Поставщик видит только действия, связанные с его товарами.
    """,
    tags=["ORDER"],
    responses={200: OrderHistorySerializer(many=True)},
    examples=[
        OpenApiExample(
            name="История заказа",
            value=[
                {
                    "id": 1,
                    "action": "item_rejected",
                    "action_display": "Товар отменён поставщиком",
                    "details": {
                        "item_id": 5,
                        "product": "iPhone 15",
                        "model": "apple/iphone/15",
                        "quantity": 1.0,
                        "shop": "Связной"
                    },
                    "user_email": "partner@example.com",
                    "created_at": "2024-04-05T10:15:00Z"
                }
            ],
            response_only=True,
        )
    ]
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsShopUserOrOwner])
def order_history_view(request, order_id):
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return Response(
            {"error": "Заказ не найден."},
            status=status.HTTP_404_NOT_FOUND
        )

    # Проверка доступа: либо владелец, либо поставщик из заказа
    if hasattr(request.user, 'shop') and request.user.shop:
        shop = request.user.shop
        has_access = order.ordered_items.filter(product_info__shop=shop).exists()
        if not has_access:
            return Response(
                {"error": "У вас нет доступа к этой истории."},
                status=status.HTTP_403_FORBIDDEN
            )
    elif order.user != request.user:
        return Response(
            {"error": "У вас нет доступа к этой истории."},
            status=status.HTTP_403_FORBIDDEN
        )

    history = OrderHistory.objects.filter(order=order).order_by("created_at")
    serializer = OrderHistorySerializer(history, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)