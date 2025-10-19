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

## Запуск приложения по умолчанию
#CMD ["/app/.venv/bin/granian", "DiplomNetologyGjango.asgi:application", "--host", "0.0.0.0", "--port", "8000"]

ENTRYPOINT ["/app/entrypoint.sh"]































#FROM python:3.12-slim-bookworm AS build
#
#COPY --from=ghcr.io/astral-sh/uv:0.8.21 /uv /uvx /bin/
#
#WORKDIR /app
#
#ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
#
## Копируем зависимости
#COPY pyproject.toml uv.lock ./
#
#RUN --mount=type=cache,target=/root/.cache/uv \
#    uv venv /app/.venv && \
#    uv sync --frozen --no-dev
#
## Копируем исходный код
#COPY . .
#
#FROM python:3.12-slim-bookworm AS runtime
#
#WORKDIR /app
#
## Копируем виртуальное окружение и код из build stage
#COPY --from=build --chown=app:app /app /app
#
## Правильно настраиваем PATH для виртуального окружения
#ENV PATH="/app/.venv/bin:$PATH" \
#    PYTHONPATH="/app" \
#    VIRTUAL_ENV="/app/.venv"
#
## Создаем пользователя
#RUN groupadd -g 1001 appgroup && \
#    useradd -u 1001 -g appgroup -m -d /app -s /bin/false appuser
#
## Исправляем формат файла и права ДО переключения пользователя
##RUN sed -i 's/\r$//' /app/entrypoint.sh && \
##    chmod +x /app/entrypoint.sh
#
## Меняем владельца файлов на appuser
#RUN chown -R appuser:appgroup /app
#
## Переключаемся на непривилегированного пользователя
#USER appuser
#
#CMD ["granian", "--interface", "wsgi", "DiplomNetologyGjango.wsgi:application", "--host", "0.0.0.0", "--port", "8000"]
##ENTRYPOINT ["/app/entrypoint.sh"]