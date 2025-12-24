from __future__ import annotations

from rest_framework import permissions


class IsShopUser(permissions.BasePermission):
    """
    Разрешает доступ только пользователям с type='shop'
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.type == "shop"
        )


class IsShopUserOrOwner(permissions.BasePermission):
    """
    Разрешает доступ:
    - Пользователю, создавшему заказ (владельцу),
    - Или поставщику (магазину), участвующему в заказе.
    """
    def has_object_permission(self, request, view, obj):
        if request.user == obj.user:
            return True
        if hasattr(request.user, "shop") and request.user.shop:
            return obj.ordered_items.filter(product_info__shop=request.user.shop).exists()
        return False
