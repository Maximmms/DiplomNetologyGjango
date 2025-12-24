from __future__ import annotations

from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from backend.models import AdminActionLog


@extend_schema(
    summary="Аудит действий (для админов)",
    description="""
Позволяет администраторам просматривать историю действий:
- Изменение статусов заказов
- Загрузка прайс-листов
- Другие системные действия

Поддерживает фильтрацию по:
- Типу действия
- Пользователю
- Времени
    """.strip(),
    tags=["ADMIN"],
    parameters=[
        OpenApiParameter("action", str, OpenApiParameter.QUERY, description="Тип действия", enum=[c[0] for c in AdminActionLog.ACTION_CHOICES]),
        OpenApiParameter("user_id", int, OpenApiParameter.QUERY, description="ID пользователя"),
        OpenApiParameter("limit", int, OpenApiParameter.QUERY, description="Ограничение количества записей", default=50),
    ],
    responses={
        200: {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "action": {"type": "string"},
                    "action_display": {"type": "string"},
                    "user": {"type": "object", "properties": {"id": {"type": "integer"}, "email": {"type": "string"}}},
                    "details": {"type": "object"},
                    "ip_address": {"type": "string"},
                    "timestamp": {"type": "string", "format": "datetime"}
                }
            }
        }
    },
    examples=[
        OpenApiExample(
            name="Пример аудита",
            value=[
                {
                    "id": 1,
                    "action": "order_status_change",
                    "action_display": "Изменение статуса заказа",
                    "user": {"id": 3, "email": "admin@site.com"},
                    "details": {
                        "order_id": 5,
                        "old_status": "new",
                        "new_status": "confirmed"
                    },
                    "ip_address": "192.168.1.1",
                    "timestamp": "2024-05-01T12:30:00Z"
                }
            ],
            response_only=True,
        )
    ]
)
@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_audit_log_view(request):
    logs = AdminActionLog.objects.all()

    action = request.query_params.get("action")
    if action and action in dict(AdminActionLog.ACTION_CHOICES):
        logs = logs.filter(action=action)

    user_id = request.query_params.get("user_id")
    if user_id:
        logs = logs.filter(user_id=user_id)

    limit = int(request.query_params.get("limit", 50))
    logs = logs.select_related("user")[:limit]

    data = []
    for log in logs:
        data.append({
            "id": log.id,
            "action": log.action,
            "action_display": log.get_action_display(),
            "user": {"id": log.user.id, "email": log.user.email} if log.user else None,
            "details": log.details,
            "ip_address": log.ip_address,
            "timestamp": log.timestamp.isoformat(),
        })

    return Response(data, status=status.HTTP_200_OK)
