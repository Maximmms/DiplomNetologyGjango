#!/bin/sh

set -e

# Применяем миграции ТОЛЬКО если это основной сервис (app)
# Избегаем дублирования в celery-worker и celery-beat
if [ "$RUN_MIGRATIONS" = "1" ]; then
    echo "⚙️ Applying migrations..."
    python manage.py makemigrations --noinput
    python manage.py migrate --noinput

    echo "📦 Collecting static files..."
    python manage.py collectstatic --noinput --clear

    # Создание суперпользователя
    if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
        echo "🔐 Checking superuser..."
        CREATED=$(python manage.py shell << END | grep 'CREATE_STATUS'
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists():
    print('CREATE_STATUS:created')
    User.objects.create_superuser(
        username='$DJANGO_SUPERUSER_USERNAME',
        email='$DJANGO_SUPERUSER_EMAIL',
        password='$DJANGO_SUPERUSER_PASSWORD'
    )
else:
    print('CREATE_STATUS:exists')
END
)
          if echo "$CREATED" | grep -q "created"; then
            echo "✅ Superuser created"
        else
            echo "✅ Superuser already exists"
            echo "📌 Login: $DJANGO_SUPERUSER_USERNAME"
        fi
    else
        echo "⚠️  Superuser env vars not set"
    fi
else
    echo "⏭️  Skipping migrations and superuser (RUN_MIGRATIONS != 1)"
fi

echo "✅ Setup complete. Executing command: $@"

exec "$@"