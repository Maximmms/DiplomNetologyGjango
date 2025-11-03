from __future__ import annotations

from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from backend.models import Shop
from backend.serializers import (
    ProductInfoSerializer,
    ShopDetailSerializer,
    ShopListSerializer,
)


@extend_schema_view(
    get=extend_schema(
        summary="Получить список магазинов",
        description="""
            Возвращает список всех активных магазинов.
            - Доступно всем.
            - Поддерживается пагинация.
            - Можно фильтровать по названию: ?search=электро
        """,
        tags=["SHOP"],
        parameters=[
            {
                "name": "search",
                "in": "query",
                "description": "Поиск магазина по названию (частичное совпадение)",
                "required": False,
                "schema": {"type": "string"},
            }
        ],
        responses={200: ShopListSerializer(many=True)},
    )
)
@method_decorator(cache_page(60 * 15), name="dispatch")
class ShopListView(generics.ListAPIView):
    queryset = Shop.objects.select_related("user").prefetch_related("categories").filter(user__is_active=True)
    serializer_class = ShopListSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get("search", None)
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by("name")

    def list(self, request, *args, **kwargs):
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
            Пример: /shops/elektronika-24/

            Поля ответа:
            - id, название, URL
            - Статус: "Принимает заказы" / "Не принимает заказы"
            - Владелец (имя или username)
            - Список категорий (id и название)

            Доступ: Все пользователи (авторизованные и нет).
        """,
        tags=["SHOP"],
        responses={200: ShopDetailSerializer, 404: "Not Found"},
        parameters=[
            {
                "name": "slug",
                "in": "path",
                "description": "Уникальный идентификатор магазина в виде строки (например, elektronika-24)",
                "required": True,
                "schema": {"type": "string"},
            }
        ],
    )
)
@method_decorator(cache_page(60 * 15), name="dispatch")
class ShopDetailView(generics.RetrieveAPIView):
    """
    Получение информации о конкретном магазине — с детализацией по категориям.
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

            Поддерживается:
            - Поиск по названию товара: `?search=iphone`
            - Фильтрация по категории: `?category_id=3`
            - Пагинация по категориям: `?page=2&page_size=10`

            Пример ответа:
            json {
                "status": true,
                "results": {
                    "Смартфоны": [
                        {
                            "id": 1,
                            "name": "iPhone 15",
                            "model": "Apple iPhone 15 Pro",
                            "price": 99990,
                            "quantity": 10
                        }
                    ],
                    "Наушники": [
                        {
                            "id": 21,
                            "name": "AirPods Pro",
                            "model": "Apple AirPods Pro 2",
                            "price": 25990,
                            "quantity": 25,
                        }
                    ]
                }
            }
            ---
            #### Особенности:
            - Доступно всем (авторизованным и неавторизованным).
            - Возвращаются только магазины с активным пользователем.
            - Категории без товаров не отображаются.
        """,
        tags=["SHOP"],
        parameters=[
            {
                "name": "slug",
                "in": "path",
                "description": "Slug магазина (например, elektronika-24)",
                "required": True,
                "schema": {"type": "string"},
            },
            {
                "name": "search",
                "in": "query",
                "description": "Поиск по названию товара (частичное совпадение)",
                "required": False,
                "schema": {"type": "string"},
            },
            {
                "name": "category_id",
                "in": "query",
                "description": "Фильтрация по ID категории",
                "required": False,
                "schema": {"type": "integer"},
            },
            {
                "name": "page",
                "in": "query",
                "description": "Номер страницы",
                "required": False,
                "schema": {"type": "integer"},
            },
            {
                "name": "page_size",
                "in": "query",
                "description": "Количество категорий на странице",
                "required": False,
                "schema": {"type": "integer"},
            },
        ],
        responses={200: ShopProductsSerializer(many=True)},
    )
)
@method_decorator(cache_page(60 * 15), name="dispatch")
class ShopProductsView(generics.ListAPIView):
    """
    Получение информации о продуктах в конкретном магазине с детализацией по категориям.
    """

    queryset = (
        Shop.objects.select_related("user")
        .prefetch_related("categories__products__product_info")
        .filter(user__is_active=True)
    )
    serializer_class = ShopProductsSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"
    lookup_url_kwarg = "slug"

    def get_object(self):
        """
        Переопределяем, чтобы корректно обработать 404
        """
        obj = super().get_object()
        self.check_object_permissions(self.request, obj)
        return obj

    def get(self, request, *args, **kwargs):
        shop = self.get_object()

        # Получаем параметры
        search = request.query_params.get("search", None)
        category_id = request.query_params.get("category_id", None)

        # Фильтруем товары
        product_infos = shop.products.select_related("product", "product__category")

        if search:
            product_infos = product_infos.filter(product__name__icontains=search)

        if category_id:
            try:
                category_id = int(category_id)
                product_infos = product_infos.filter(product__category_id=category_id)
            except ValueError:
                return Response(
                    {"status": False, "error": "Invalid category_id"}, status=400
                )

        # Группируем по категориям
        categories_dict = {}
        for pi in product_infos.order_by("product__category__name", "product__name"):
            category = pi.product.category
            if category not in categories_dict:
                categories_dict[category] = []
            categories_dict[category].append(pi)

        # Пагинация
        paginator = self.pagination_class()
        paginated_categories = paginator.paginate_queryset(
            list(categories_dict.keys()), request, view=self
        )

        # Собираем данные
        results = {}
        for category in paginated_categories:
            results[category.name] = ProductInfoSerializer(
                [item.product_info for item in categories_dict[category]], many=True
            ).data

        return paginator.get_paginated_response({
            "status": True,
            "results": results
        })