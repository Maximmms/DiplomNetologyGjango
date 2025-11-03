from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from backend.views.user_views import (
    UserChangePasswordViewSet,
    UserContactViewSet,
    UserEmailConfirmationViewSet,
    UserEmailStatusAPIView,
    UserLoginViewSet,
    UserLogoutViewSet,
    UserProfileViewSet,
    UserRegisterViewSet,
)

router = SimpleRouter()

def register_user_urls(router):
    router.register(r"register", UserRegisterViewSet, basename="register")
    router.register(r"login", UserLoginViewSet, basename="login")
    router.register(r"logout", UserLogoutViewSet, basename="logout")
    router.register(r"password", UserChangePasswordViewSet, basename="password")
    router.register(r"contacts", UserContactViewSet, basename="contacts")
    router.register(r"profile", UserProfileViewSet, basename="profile")
    router.register(r"email", UserEmailConfirmationViewSet, basename="email-confirm")

register_user_urls(router)

urlpatterns = [
    path("", include(router.urls)),
    path("email/status/", UserEmailStatusAPIView.as_view(), name="user_email_status"),
]

app_name = "user"
