from __future__ import annotations

from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.generics import GenericAPIView
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
            Возвращает список всех магазинов с возможностью поиска и фильтрации.

            ---
            #### Параметры:
            - `search` — частичное совпадение по названию магазина
            - `category_id` — магазины, связанные с указанной категорией
            - `page`, `page_size` — пагинация
        """,
        tags=["SHOP"],
        parameters=[
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Поиск магазина по названию (частичное совпадение)",
                required=False
            ),
            OpenApiParameter(
                name="category_id",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Фильтрация по ID категории",
                required=False
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Номер страницы",
                required=False
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Количество магазинов на странице",
                required=False
            ),
        ],
        responses={200: ShopListSerializer(many=True)},
        operation_id="shop_list",
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
        description="Возвращает товары магазина, сгруппированные по категориям.",
        tags=["SHOP"],
        parameters=[
            OpenApiParameter("slug", str, OpenApiParameter.PATH, "Slug магазина", True),
            OpenApiParameter("search", str, OpenApiParameter.QUERY, "Поиск по названию товара", False),
            OpenApiParameter("category_id", int, OpenApiParameter.QUERY, "Фильтрация по ID категории", False),
            OpenApiParameter("page", int, OpenApiParameter.QUERY, "Номер страницы", False),
            OpenApiParameter("page_size", int, OpenApiParameter.QUERY, "Количество категорий на странице", False),
        ],
        responses={200: dict},
        operation_id="shop_products",
    )
)
@method_decorator(cache_page(60 * 15), name="dispatch")
class ShopProductsView(GenericAPIView):
    """
    Получение товаров магазина, сгруппированных по категориям.
    Поддерживает поиск, фильтрацию и пагинацию по категориям.
    """

    queryset = (
        Shop.objects.select_related("user")
        .prefetch_related("categories__products__product_info")
        .filter(user__is_active=True)
    )
    serializer_class = ProductInfoSerializer
    permission_classes = [AllowAny]
    pagination_class = CategoryPagination
    lookup_field = "slug"
    lookup_url_kwarg = "slug"

    def get_object(self):
        """
        Получаем магазин по slug.
        """
        queryset = self.get_queryset()
        filter_kwargs = {self.lookup_field: self.kwargs[self.lookup_url_kwarg]}
        obj = generics.get_object_or_404(queryset, **filter_kwargs)
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
            except (ValueError, TypeError):
                return Response(
                    {"status": False, "error": "Invalid category_id"},
                    status=status.HTTP_400_BAD_REQUEST
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