from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from backend.views.user_views import (
    UserChangePasswordViewSet,
    UserContactViewSet,
    UserEmailConfirmationViewSet,
    UserEmailStatusViewSet,
    UserLoginViewSet,
    UserLogoutViewSet,
    UserProfileViewSet,
    UserRegisterViewSet,
)

# Инициализируем роутер и регистрируем ViewSet'ы
router = DefaultRouter()
router.register(r"user/register", UserRegisterViewSet, basename="register")
router.register(r"user/register", UserEmailConfirmationViewSet, basename="email-confirmation")
router.register(r"user/password", UserChangePasswordViewSet, basename="password")
router.register(r"user/login", UserLoginViewSet, basename="login")
router.register(r"user/logout", UserLogoutViewSet, basename="logout")
router.register(r"user/profile", UserProfileViewSet, basename="profile")
router.register(r"user/contacts", UserContactViewSet, basename="contacts")




app_name = "backend"

urlpatterns = [
    path("", include(router.urls)),
    path("user/register/email/status/", UserEmailStatusViewSet.as_view({"get": "status"}), name="email-status"),
]
