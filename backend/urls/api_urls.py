from __future__ import annotations

from django.urls import include, path

urlpatterns = [
    path("user/", include("backend.urls.user_urls", namespace="user")),
    path("shop/", include("backend.urls.shop_urls", namespace="shop")),
    path("order/", include("backend.urls.order_urls", namespace="oeder")),
    path("partners/", include("backend.urls.partner_urls", namespace="partner")),
]
