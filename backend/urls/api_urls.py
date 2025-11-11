from __future__ import annotations

from django.urls import include, path

urlpatterns = [
    path("user/", include("backend.urls.user_urls", namespace="USER")),
    path("shop/", include("backend.urls.shop_urls", namespace="SHOP")),
    path("order/", include("backend.urls.order_urls", namespace="ORDER")),
    path("partners/", include("backend.urls.partner_urls", namespace="PARTNERS")),
    path("basket/", include("backend.urls.basket_urls", namespace="BASKET")),
]
