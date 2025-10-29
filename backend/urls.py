from __future__ import annotations

from django.urls import path

from backend import views
from backend.views import UserRegisterView

app_name = "backend"
urlpatterns = [
    path("hello", views.hello_view, name="hello"),
    path("user/register/", UserRegisterView.as_view(), name="register"),
    path("partner/update/", views.PriceUpdateView.as_view(), name="price_update"),
    path("user/login/", views.UserLoginView.as_view(), name="login"),
    path("user/logout/", views.UserLogoutView.as_view(), name="logout"),
]
