# Используем образ с uv и Python
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Рабочая директория
WORKDIR /app

# Настройки uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app"

# Копируем зависимости для их установки
COPY pyproject.toml uv.lock ./

# Устанавливаем зависимости, используя кэш
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Копируем весь проект
COPY . .

# Устанавливаем проект
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Подготавливаем entrypoint.sh
RUN sed -i 's/\r$//' ./entrypoint.sh && \
    chmod +x ./entrypoint.sh

# Точка входа
ENTRYPOINT ["./entrypoint.sh"]