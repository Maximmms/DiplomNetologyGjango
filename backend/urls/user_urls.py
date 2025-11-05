from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from backend.views.user_views import (
    UserChangePasswordViewSet,
    UserContactViewSet,
    UserEmailConfirmationViewSet,
    UserEmailStatusAPIView,
    UserLoginView,
    UserLogoutViewSet,
    UserProfileViewSet,
    UserRegisterViewSet,
)

router = SimpleRouter()

def register_user_urls(router):
    router.register(r"register", UserRegisterViewSet, basename="register")
    router.register(r"logout", UserLogoutViewSet, basename="logout")
    router.register(r"password", UserChangePasswordViewSet, basename="password")
    router.register(r"profile", UserProfileViewSet, basename="profile")
    router.register(r"email", UserEmailConfirmationViewSet, basename="email-confirm")

register_user_urls(router)

urlpatterns = [
    path("", include(router.urls)),
    path(
        "contact/<int:pk>/",
        UserContactViewSet.as_view(
            {"put": "update", "patch": "partial_update", "delete": "destroy"}
        ),
        name="contact-detail",
    ),
    path("email/status/", UserEmailStatusAPIView.as_view(), name="user_email_status"),
    path("login/", UserLoginView.as_view(), name="login"),
]

app_name = "user"