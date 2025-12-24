from __future__ import annotations

from django.urls import include, path

from backend.views.admin_views import admin_audit_log_view

app_name = "ADMIN"

urlpatterns = [
    path('audit/', admin_audit_log_view, name = 'admin_audit_log'),
]