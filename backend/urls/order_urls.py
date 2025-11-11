from __future__ import annotations

from django.urls import path

from backend.views.order_views import (
    CreateOrderFromBasketView,
    DeleteOrderView,
    PlaceOrderView,
    UserOrdersView,
)

app_name = "ORDER"

urlpatterns = [
    path("", UserOrdersView.as_view(), name="user_orders"),
    path("create/", CreateOrderFromBasketView.as_view(), name="order-create"),
    path("delete/", DeleteOrderView.as_view(), name="order-delete"),
    path("place/", PlaceOrderView.as_view(), name="order-place"),
]
