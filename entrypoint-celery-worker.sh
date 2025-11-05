#!/bin/sh
set -e

echo "⏳ Waiting for database and redis..."

# 🔍 Определяем путь к python в зависимости от ОС
PYTHON_PATH=""
if [ -f "/app/.venv/bin/python" ]; then
    PYTHON_PATH="/app/.venv/bin/python"
elif [ -f "/app/.venv/Scripts/python.exe" ]; then
    PYTHON_PATH="/app/.venv/Scripts/python.exe"
elif [ -f "/app/.venv/Scripts/python" ]; then
    PYTHON_PATH="/app/.venv/Scripts/python"
else
    echo "❌ Не найден ни один из путей:"
    echo "   - /app/.venv/bin/python"
    echo "   - /app/.venv/Scripts/python.exe"
    echo "   - /app/.venv/Scripts/python"
    exit 1
fi

# Отладка
echo "🔍 PATH: $PATH"
echo "📂 Содержимое /app/.venv:"
ls -la /app/.venv

echo "✅ Найден Python: $PYTHON_PATH"

# Проверка, импортируется ли redis
if ! "$PYTHON_PATH" -c "import redis" 2>/dev/null; then
    echo "❌ Модуль 'redis' не установлен"
    "$PYTHON_PATH" -m pip list
    exit 1
fi

echo "✅ Модуль 'redis' импортируется"

# Функция для проверки PostgreSQL
wait_for_postgres() {
    host="$1"
    port="$2"
    for i in $(seq 1 30); do
        if "$PYTHON_PATH" -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect(('$host', $port))
    s.close()
    exit(0)
except (socket.timeout, socket.error):
    exit(1)
"; then
            echo "✅ PostgreSQL is ready!"
            return 0
        fi
        echo "🟡 Waiting for PostgreSQL... $i/30"
        sleep 2
    done
    echo "❌ PostgreSQL not available"
    return 1
}

# Функция для проверки Redis
wait_for_redis() {
    host="$1"
    port="$2"
    for i in $(seq 1 30); do
        if "$PYTHON_PATH" -c "
import redis
try:
    client = redis.Redis(host='$host', port=$port, socket_connect_timeout=2)
    client.ping()
    client.close()
    exit(0)
except Exception as e:
    print(f'Redis error: {e}')
    exit(1)
"; then
            echo "✅ Redis is ready!"
            return 0
        fi
        echo "🟡 Waiting for Redis... $i/30"
        sleep 2
    done
    echo "❌ Redis not available"
    return 1
}

# Ждём БД и Redis
wait_for_postgres 'db' 5432
wait_for_redis 'redis' 6379

echo "✅ Dependencies are ready. Applying migrations..."
"$PYTHON_PATH" manage.py migrate --noinput

echo "🚀 Starting Celery worker..."
exec "$PYTHON" -m celery -A DiplomNetologyGjango worker -l INFO