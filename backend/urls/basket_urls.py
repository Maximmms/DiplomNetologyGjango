from __future__ import annotations

from django.urls import path

from backend.views.basket_views import BasketAddView, BasketRemoveView, BasketView

app_name = "BASKET"

urlpatterns = [
    path("", BasketView.as_view(), name="basket_get"),
    path("add/", BasketAddView.as_view(), name="basket_add"),
    path("remove/", BasketRemoveView.as_view(), name="basket_remove"),
]
