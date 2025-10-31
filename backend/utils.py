from __future__ import annotations


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
