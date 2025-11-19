from __future__ import annotations

from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import generics, serializers, status
from rest_framework.generics import GenericAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from backend.models import Category, ProductInfo, Shop
from backend.serializers import (
    CategorySerializer,
    ProductInfoSearchSerializer,
    ProductInfoSerializer,
    ShopDetailSerializer,
    ShopListSerializer,
)


@extend_schema_view(
    get=extend_schema(
        summary="Получить список магазинов",
        description="""
Возвращает список всех магазинов с возможностью поиска и фильтрации.

#### Параметры:
- `search` — частичное совпадение по названию магазина
- `category_id` — магазины, связанные с указанной категорией
- `page`, `page_size` — пагинация
        """.strip(),
        tags=["SHOP"],
        parameters=[
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Поиск магазина по названию (частичное совпадение)",
                required=False,
            ),
            OpenApiParameter(
                name="category_id",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Фильтрация по ID категории",
                required=False,
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Номер страницы",
                required=False,
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Количество магазинов на странице",
                required=False,
            ),
        ],
        responses={200: ShopListSerializer(many=True)},
        examples=[
            OpenApiExample(
                name="Список магазинов",
                summary="Пример ответа со списком магазинов",
                value={
                    "status": True,
                    "results": [
                        {
                            "id": 1,
                            "name": "Электроника-24",
                            "slug": "elektronika-24",
                            "url": "https://example.com/shop.xml",
                            "state": True,
                            "state_display": "Принимает заказы",
                            "user": "shop_user",
                            "categories": [
                                {"id": 1, "name": "Смартфоны"},
                                {"id": 2, "name": "Наушники"}
                            ]
                        }
                    ]
                },
                response_only=True,
            ),
            OpenApiExample(
                name="Пример запроса с параметрами",
                summary="GET /api/shop/?search=электроника&page=1",
                description="Пример вызова с query-параметрами",
                value=None,
                request_only=True,
            )
        ],
        operation_id="shop_list",
    )
)
@method_decorator(cache_page(60 * 15), name="dispatch")
class ShopListView(generics.ListAPIView):
    """
    Возвращает список всех активных магазинов.
    Поддерживает фильтрацию по названию и категории, а также пагинацию.
    Доступ: все пользователи.
    """
    queryset = Shop.objects.select_related("user").prefetch_related("categories").filter(user__is_active=True)
    serializer_class = ShopListSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        """
        Возвращает отфильтрованный по поисковому запросу queryset магазинов.
        """
        queryset = super().get_queryset()
        search = self.request.query_params.get("search", None)
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by("name")

    def list(self, request, *args, **kwargs):
        """
        Переопределённый метод для формирования ответа.
        Добавляет обёртку {"status": True, "results": [...]}.
        """
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response({"status": True, "results": serializer.data}, status=200)


@extend_schema_view(
    get=extend_schema(
        summary="Получить информацию о магазине",
        description="""
Возвращает подробную информацию о магазине по его slug.

### Поля ответа:
- id, название, URL
- Статус: "Принимает заказы" / "Не принимает заказы"
- Владелец (имя или username)
- Список категорий (id и название)

Доступ: Все пользователи (авторизованные и нет).
        """.strip(),
        tags=["SHOP"],
        responses={200: ShopDetailSerializer, 404: {"type": "object", "properties": {}}},
        parameters=[
            OpenApiParameter(
                name="slug",
                type=str,
                location=OpenApiParameter.PATH,
                description="Уникальный идентификатор магазина в виде строки (например, elektronika-24)",
                required=True,
            )
        ],
        examples=[
            OpenApiExample(
                name="Детали магазина",
                summary="Пример ответа с информацией о магазине",
                value={
                    "id": 1,
                    "name": "Электроника-24",
                    "slug": "elektronika-24",
                    "url": "https://example.com/shop.xml",
                    "state": True,
                    "state_display": "Принимает заказы",
                    "user": "shop_user",
                    "categories": [
                        {"id": 1, "name": "Смартфоны"},
                        {"id": 2, "name": "Наушники"}
                    ]
                },
                response_only=True,
            )
        ],
        operation_id="shop_retrieve",
    )
)
@method_decorator(cache_page(60 * 15), name="dispatch")
class ShopDetailView(generics.RetrieveAPIView):
    """
    Получение детальной информации о магазине по его slug.
    Возвращается только активный магазин.
    Доступ: все пользователи.
    """
    queryset = (
        Shop.objects.select_related("user")
        .prefetch_related("categories")
        .filter(user__is_active=True)
    )
    serializer_class = ShopDetailSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"
    lookup_url_kwarg = "slug"


class CategoryPagination(PageNumberPagination):
    """
    Пагинатор для категорий.
    Поддерживает настройку количества элементов на странице.
    """
    page_size = 5
    page_size_query_param = "page_size"
    max_page_size = 50
    page_query_param = "page"
    ordering = "name"


@extend_schema_view(
    get=extend_schema(
        summary="Получить продукты магазина по категориям",
        description="""
Возвращает товары магазина, сгруппированные по категориям.

#### Параметры:
- `slug` — идентификатор магазина
- `search` — поиск по названию товара
- `category_id` — фильтрация по ID категории
- `page`, `page_size` — пагинация по категориям
        """.strip(),
        tags=["SHOP"],
        parameters=[
            OpenApiParameter("slug", str, OpenApiParameter.PATH, "Slug магазина", True),
            OpenApiParameter("search", str, OpenApiParameter.QUERY, "Поиск по названию товара", False),
            OpenApiParameter("category_id", int, OpenApiParameter.QUERY, "Фильтрация по ID категории", False),
            OpenApiParameter("page", int, OpenApiParameter.QUERY, "Номер страницы", False),
            OpenApiParameter("page_size", int, OpenApiParameter.QUERY, "Количество категорий на странице", False),
        ],
        responses={200: {"type": "object", "properties": {"status": {"type": "boolean"}, "results": {"type": "object"}}}},
        examples=[
            OpenApiExample(
                name="Товары магазина",
                summary="Пример ответа с товарами по категориям",
                value={
                    "status": True,
                    "results": {
                        "Смартфоны": [
                            {
                                "id": 1,
                                "name": "iPhone 15",
                                "model": "Apple iPhone 15 128GB",
                                "price": 100000,
                                "price_rrc": 105000,
                                "quantity": 10,
                                "parameters": [
                                    {"parameter": "Цвет", "value": "Чёрный"},
                                    {"parameter": "ОЗУ", "value": "6 ГБ"}
                                ]
                            }
                        ],
                        "Наушники": [
                            {
                                "id": 2,
                                "name": "AirPods Pro",
                                "model": "Apple AirPods Pro",
                                "price": 25000,
                                "price_rrc": 27000,
                                "quantity": 5,
                                "parameters": [
                                    {"parameter": "Тип", "value": "Беспроводные"}
                                ]
                            }
                        ]
                    }
                },
                response_only=True,
            ),
            OpenApiExample(
                name="Пример запроса с параметрами",
                summary="GET /api/shop/products/elektronika-24/?search=iPhone&category_id=1",
                description="Пример вызова с query-параметрами",
                value=None,
                request_only=True,
            )
        ],
        operation_id="shop_products",
    )
)
@method_decorator(cache_page(60 * 15), name="dispatch")
class ShopProductsView(GenericAPIView):
    """
    Возвращает список товаров магазина, сгруппированных по категориям.
    Поддерживает поиск, фильтрацию и пагинацию.
    Доступ: все пользователи.
    """
    queryset = (
        Shop.objects.select_related("user")
        .prefetch_related("categories")
        .filter(user__is_active=True)
    )
    serializer_class = ProductInfoSerializer
    permission_classes = [AllowAny]
    pagination_class = CategoryPagination
    lookup_field = "slug"
    lookup_url_kwarg = "slug"

    def get_object(self):
        """
        Получает магазин по `slug` из URL.
        Возвращает 404, если магазин не найден или неактивен.
        """
        queryset = self.get_queryset()
        filter_kwargs = {self.lookup_field: self.kwargs[self.lookup_url_kwarg]}
        obj = generics.get_object_or_404(queryset, **filter_kwargs)
        self.check_object_permissions(self.request, obj)
        return obj

    def get(self, request, *args, **kwargs):
        """
        Обрабатывает GET-запрос:
        - Получает магазин
        - Фильтрует товары по поиску и категории
        - Группирует по категориям
        - Применяет пагинацию
        - Возвращает структурированный ответ
        """
        shop = self.get_object()

        search = request.query_params.get("search", None)
        category_id = request.query_params.get("category_id", None)

        product_infos = (
            ProductInfo.objects.filter(shop=shop, quantity__gt=0)
            .select_related("product", "product__category")
            .prefetch_related("product_parameters__parameter")
            .order_by("product__category__name", "product__name")
        )

        if search:
            product_infos = product_infos.filter(product__name__icontains=search)

        if category_id:
            try:
                category_id = int(category_id)
                product_infos = product_infos.filter(product__category_id=category_id)
            except (ValueError, TypeError):
                return Response(
                    {"status": False, "error": "Invalid category_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        categories_dict = {}
        for pi in product_infos.order_by("product__category__name", "product__name"):
            category = pi.product.category
            if category not in categories_dict:
                categories_dict[category] = []
            categories_dict[category].append(pi)

        paginator = self.pagination_class()
        paginated_categories = paginator.paginate_queryset(
            list(categories_dict.keys()), request, view=self
        )

        results = {}
        for category in paginated_categories:
            results[category.name] = ProductInfoSerializer(
                [item.product_info for item in categories_dict[category]], many=True
            ).data

        return paginator.get_paginated_response({
            "status": True,
            "results": results
        })


@extend_schema_view(
    get=extend_schema(
        summary="Поиск товаров по магазинам",
        description="""
Выполняет поиск товаров по названию по всем магазинам.

#### Параметры:
- `search` — ключевое слово для поиска (обязательный)
- `page`, `page_size` — пагинация
    """.strip(),
        tags=["SHOP"],
        parameters=[
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Ключевое слово для поиска товара",
                required=True,
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Номер страницы",
                required=False,
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Количество результатов на странице",
                required=False,
            ),
        ],
        responses={
            200: inline_serializer(
                name="ProductInfoSearchResponse",
                fields={
                    "count": serializers.IntegerField(help_text="Общее количество результатов"),
                    "next": serializers.URLField(help_text="Ссылка на следующую страницу", required=False, allow_null=True),
                    "previous": serializers.URLField(help_text="Ссылка на предыдущую страницу", required=False, allow_null=True),
                    "results": inline_serializer(
                        name="ProductInfoSearchResult",
                        fields=ProductInfoSearchSerializer().get_fields()
                    ),
                },
            ),
        },
        examples=[
            OpenApiExample(
                name="Пример запроса поиска",
                summary="GET /api/shop/search/?search=iPhone&page=1",
                description="Пример вызова с параметрами",
                value=None,
                request_only=True,
            ),
            OpenApiExample(
                name="Результаты поиска",
                summary="Пример ответа с результатами поиска",
                value={
                    "count": 2,
                    "next": None,
                    "previous": None,
                    "results": [
                        {
                            "id": 1,
                            "name": "iPhone 15",
                            "model": "Apple iPhone 15 128GB",
                            "price": 100000,
                            "shop": "Электроника-24",
                            "shop_state": True,
                            "category": "Смартфоны"
                        },
                        {
                            "id": 3,
                            "name": "iPhone 14",
                            "model": "Apple iPhone 14 128GB",
                            "price": 85000,
                            "shop": "ТехноМир",
                            "shop_state": True,
                            "category": "Смартфоны"
                        }
                    ]
                },
                response_only=True,
            )
        ],
        operation_id="product_search",
    )
)
class ShopProductSearchView(generics.ListAPIView):
    """
    Поиск товаров по названию по всем активным магазинам.
    Поддерживает пагинацию.
    Доступ: все пользователи.
    """
    serializer_class = ProductInfoSearchSerializer
    permission_classes = [AllowAny]
    pagination_class = PageNumberPagination

    def get_queryset(self):
        request = self.request
        search = request.query_params.get("search", "").strip()
        if not search:
            return ProductInfo.objects.none()

        queryset = (
            ProductInfo.objects.select_related("product", "shop")
            .filter(shop__user__is_active=True, shop__state=True, quantity__gt=0)
            .prefetch_related("product_parameters__parameter")
            .distinct()
        )

        return queryset.filter(
            Q(product__name__icontains=search)
            | Q(model__icontains=search)
            | Q(product_parameters__parameter__name__icontains=search)
            | Q(product_parameters__value__icontains=search)
        ).order_by("product__name")

    def list(self, request, *args, **kwargs):
        search = request.query_params.get("search", "").strip()
        if not search:
            return Response(
                {"error": "Требуется параметр 'search'"},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().list(request, *args, **kwargs)

@extend_schema_view(
    get=extend_schema(
        summary="Получить список всех категорий",
        description="""
Возвращает список всех категорий товаров в системе.

#### Параметры:
- `search` — фильтрация по частичному совпадению с названием категории
- `page`, `page_size` — пагинация
        """.strip(),
        tags=["SHOP"],
        parameters=[
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Поиск по названию категории (частичное совпадение)",
                required=False,
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Номер страницы",
                required=False,
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Количество категорий на странице",
                required=False,
            ),
        ],
        responses=inline_serializer(
            name="CategoryListResponse",
            fields={
                "count": serializers.IntegerField(help_text="Общее количество категорий"),
                "next": serializers.URLField(help_text="Ссылка на следующую страницу", required=False, allow_null=True),
                "previous": serializers.URLField(help_text="Ссылка на предыдущую страницу", required=False, allow_null=True),
                "results": inline_serializer(
                    name="CategoryItem",
                    fields=CategorySerializer().get_fields()
                ),
            },
        ),
        examples=[
            OpenApiExample(
                name="Список категорий",
                summary="Пример ответа со списком категорий",
                value={
                    "count": 3,
                    "next": None,
                    "previous": None,
                    "results": [
                        {"id": 1, "name": "Смартфоны"},
                        {"id": 2, "name": "Ноутбуки"},
                        {"id": 3, "name": "Наушники"}
                    ]
                },
                response_only=True,
            ),
            OpenApiExample(
                name="Пример запроса с поиском",
                summary="GET /api/shop/categories/?search=смарт",
                description="Пример вызова с параметром search",
                value=None,
                request_only=True,
            )
        ],
        operation_id="category_list",
    )
)
class CategoryListView(generics.ListAPIView):
    """
    Возвращает список всех категорий с возможностью поиска и пагинации.
    Доступ: все пользователи.
    """
    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    pagination_class = PageNumberPagination

    def get_queryset(self):
        """
        Возвращает отфильтрованный по поисковому запросу queryset категорий.
        """
        queryset = super().get_queryset()
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset

    def list(self, request, *args, **kwargs):
        """
        Переопределённый метод для возврата ответа в формате:
        {"count", "next", "previous", "results"}
        """
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response({"count": queryset.count(), "next": None, "previous": None, "results": serializer.data})
