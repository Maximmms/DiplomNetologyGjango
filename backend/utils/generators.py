from __future__ import annotations

import secrets
import string


def generate_code(length=12):
    """Генерация случайного кода длиной length символов."""
    characters = string.ascii_letters + string.digits
    code = "".join(secrets.choice(characters) for _ in range(length))
    return code
