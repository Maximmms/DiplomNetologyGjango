from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from backend.views.shop_views import ShopDetailView, ShopListView, ShopProductsView

router = SimpleRouter()

def register_shop_urls(router):
    pass

register_shop_urls(router)

urlpatterns = [
    path("", include(router.urls)),
    path("list", ShopListView.as_view(), name="shop-list"),
    path("<slug:slug>", ShopDetailView.as_view(), name="shop-detail"),
    path("<slug:slug>/products", ShopProductsView.as_view(), name="shop-products"),
]

app_name = "shop"
