from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import SimpleRouter

router = SimpleRouter()

def register_partner_urls(router):
    pass

register_partner_urls(router)

urlpatterns = [
    path("", include(router.urls)),
]

app_name = "partner"
