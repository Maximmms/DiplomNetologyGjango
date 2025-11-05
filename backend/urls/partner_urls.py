from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from backend.views.partners_views import PartnerPriceUploadView

router = SimpleRouter()

def register_partner_urls(router):
    pass

register_partner_urls(router)

urlpatterns = [
    path("", include(router.urls)),
    path("price/upload", PartnerPriceUploadView.as_view(), name="price_upload"),
]

app_name = "partner"
