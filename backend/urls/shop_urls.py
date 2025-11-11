from __future__ import annotations

from django.urls import path

from backend.views.shop_views import (
    CategoryListView,
    ShopDetailView,
    ShopListView,
    ShopProductSearchView,
    ShopProductsView,
)

app_name = "SHOP"

urlpatterns = [
    path("list", ShopListView.as_view(), name="shop-list"),
    path("<slug:slug>", ShopDetailView.as_view(), name="shop-detail"),
    path("<slug:slug>/products", ShopProductsView.as_view(), name="shop-products"),
    path("search/", ShopProductSearchView.as_view(), name="product_search"),
    path("category/", CategoryListView.as_view(), name="category-list"),
]
