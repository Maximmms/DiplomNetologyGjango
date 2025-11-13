from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from backend.views.user_views import (
    UserChangeEmailRequestView,
    UserChangePasswordViewSet,
    UserContactViewSet,
    UserLoginView,
    UserLogoutViewSet,
    UserProfileViewSet,
    UserRegisterViewSet,
    UserSendEmailConfirmationView,
    UserVerifyEmailChangeView,
    UserVerifyEmailConfirmationView,
)

router = SimpleRouter()

def register_user_urls(router):
    router.register(r"register", UserRegisterViewSet, basename="register")
    router.register(r"logout", UserLogoutViewSet, basename="logout")
    router.register(r"password", UserChangePasswordViewSet, basename="password")
    router.register(r"contact", UserContactViewSet, basename="contact")
    router.register(r"profile", UserProfileViewSet, basename="profile")

app_name = "USER"

register_user_urls(router)

urlpatterns = [
    path("", include(router.urls)),
    path(
        "email/send/", UserSendEmailConfirmationView.as_view(), name="user_email_send"
    ),
    path(
        "email/verify/",
        UserVerifyEmailConfirmationView.as_view(),
        name="user_verify_email_confirmation",
    ),
    path(
        "email/change/request/",
        UserChangeEmailRequestView.as_view(),
        name="user_change_email_request",
    ),
    path(
        "email/change/verify/",
        UserVerifyEmailChangeView.as_view(),
        name="user_verify_email_change",
    ),
    path("login/", UserLoginView.as_view(), name="login"),
    # path(
    #     "contact/<int:id>/",
    #     UserContactViewSet.as_view(
    #         {"put": "update", "patch": "partial_update", "delete": "destroy"}
    #     ),
    #     name="user_contact_detail",
    # ),
]