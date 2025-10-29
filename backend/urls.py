from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from backend.views import (
    UserLoginViewSet,
    UserLogoutViewSet,
    UserRegisterViewSet,
)

# Инициализируем роутер и регистрируем ViewSet'ы
router = DefaultRouter()
router.register(r"user/register", UserRegisterViewSet, basename="register")
router.register(r"user/login", UserLoginViewSet, basename="login")
router.register(r"user/logout", UserLogoutViewSet, basename="logout")


app_name = "backend"

urlpatterns = [
    path("", include(router.urls)),
]