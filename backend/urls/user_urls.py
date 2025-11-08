from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from backend.views.user_views import (
    UserChangePasswordViewSet,
    UserContactViewSet,
    UserLoginView,
    UserLogoutViewSet,
    UserProfileViewSet,
    UserRegisterViewSet,
    UserSendEmailConfirmationView,
    UserVerifyEmailConfirmationView,
)

router = SimpleRouter()

def register_user_urls(router):
    router.register(r"register", UserRegisterViewSet, basename="register")
    router.register(r"logout", UserLogoutViewSet, basename="logout")
    router.register(r"password", UserChangePasswordViewSet, basename="password")
    router.register(r"profile", UserProfileViewSet, basename="profile")


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
    path("email/send/", UserSendEmailConfirmationView.as_view(), name="user_email_send"),
    path("email/verify/", UserVerifyEmailConfirmationView.as_view(), name="user_email_verify"),
    path("login/", UserLoginView.as_view(), name="login"),
]

app_name = "user"