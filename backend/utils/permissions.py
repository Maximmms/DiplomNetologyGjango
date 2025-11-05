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
