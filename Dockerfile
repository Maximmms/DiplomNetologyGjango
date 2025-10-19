# Используем образ с uv и Python
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Рабочая директория
WORKDIR /app

# Настройки uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Устанавливаем зависимости, используя кэш
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-install-project --no-dev

# Копируем остальной код
ADD . /app

# Устанавливаем проект
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Добавляем виртуальное окружение в PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app"

RUN sed -i 's/\r$//' /app/entrypoint.sh && \
    chmod +x /app/entrypoint.sh


ENTRYPOINT ["/app/entrypoint.sh"]