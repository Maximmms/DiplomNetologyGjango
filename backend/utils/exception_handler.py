from __future__ import annotations

from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        return response

    error_detail = response.data

    if isinstance(error_detail, list):
        message = ", ".join([str(e) for e in error_detail])
    elif isinstance(error_detail, dict):
        messages = []
        for key, value in error_detail.items():
            if isinstance(value, list):
                messages.append(f"{key}: {', '.join([str(v) for v in value])}")
            else:
                messages.append(f"{key}: {str(value)}")
        message = "; ".join(messages)
    else:
        message = str(error_detail)

    # Формируем кастомный JSON
    custom_response_data = {
        "error": message,
        "status": response.status_code,
    }

    response.data = custom_response_data
    return response
