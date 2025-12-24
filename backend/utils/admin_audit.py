from __future__ import annotations

from django.http import HttpRequest

from backend.models import AdminActionLog


def log_admin_action(
    user,
    action: str,
    details: dict,
    request: HttpRequest = None,
):
    """
    Логирует действие администратора.
    """
    if action not in dict(AdminActionLog.ACTION_CHOICES):
        action = "other"

    log_data = {
        "action": action,
        "user": user,
        "details": details,
    }

    if request:
        log_data["ip_address"] = get_client_ip(request)
        log_data["user_agent"] = request.META.get("HTTP_USER_AGENT", "")[:1000]

    AdminActionLog.objects.create(**log_data)


def get_client_ip(request: HttpRequest) -> str:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip
