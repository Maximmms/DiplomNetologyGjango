from __future__ import annotations

from django.urls import path

from backend.views.partners_views import (
    PartnerConfirmOrderView,
    PartnerOrdersView,
    PartnerPriceUploadView,
    PartnerShopStateView,
)

app_name = "PARTNERS"

urlpatterns = [
    path("price/upload", PartnerPriceUploadView.as_view(), name="price_upload"),
    path("state/", PartnerShopStateView.as_view(), name ="partner_shop_state"),
    path("partner/orders/", PartnerOrdersView.as_view(), name="partner-orders"),
path("partner/order/confirm/", PartnerConfirmOrderView.as_view(), name="partner-order-confirm"),
]
