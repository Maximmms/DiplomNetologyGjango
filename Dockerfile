# Используем образ с uv и Python
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Настройки uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app"

# Копируем зависимости для их установки
COPY pyproject.toml uv.lock ./

# Очистка кэша
RUN rm -rf /root/.cache/uv

# Создаём виртуальное окружение и устанавливаем зависимости
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv .venv --python python3.12 && \
    uv pip install --upgrade pip && \
    uv sync --frozen --no-dev

# Копируем весь проект
COPY . .

RUN mkdir -p /app/logs

RUN cp -r .venv /tmp/venv-final && \
    rm -rf .venv && \
    mv /tmp/venv-final .venv

# Делаем entrypoint'ы исполняемыми
RUN find . -name "entrypoint*.sh" -exec chmod +x {} \; 2>/dev/null || true

# Точка входа
ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "DiplomNetologyGjango.asgi:application", "--host", "0.0.0.0", "--port", "8000"]