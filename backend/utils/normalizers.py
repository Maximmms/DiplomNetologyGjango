from __future__ import annotations

import re

from rest_framework import serializers


def validate_phone_number(value: str) -> str:
    digits = "".join(filter(str.isdigit, value))

    if len(digits) != 11:
        raise serializers.ValidationError("Неверный формат номера. Пример: +7 (999) 123-45-67")

    if not digits.startswith("7"):
        raise serializers.ValidationError("Номер должен быть в формате РФ (начинаться с 7)")

    return digits

def normalize_phone_number(raw_number):
    """Преобразует любой формат номера в +7XXXXXXXXXX"""
    if not raw_number:
        return ""
    # Удаляем всё, кроме цифр
    digits = "".join(filter(str.isdigit, raw_number))

    # Убираем ведущий 8, если есть, и приводим к формату +7
    if len(digits) == 11:
        if digits[0] == "8":
            digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    elif len(digits) == 10:  # если уже +7, но без +
        pass

    # Проверим длину: должно быть 11 цифр после +7
    if len(digits) != 11 or not digits.startswith("7"):
        # Можно вернуть как есть или бросить исключение
        return raw_number  # или вернуть None, если хотите отклонить

    return f"+{digits}"


def is_valid_email(email: str) -> bool:
    """
    Проверяет, является ли строка корректным email.
    """
    if not email:
        return False
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None

def normalize_email(email: str) -> str:
    """
    Нормализует email: убирает лишние пробелы, приводит к lowercase.
    """
    if not email:
        return ""
    return email.strip().lower()
