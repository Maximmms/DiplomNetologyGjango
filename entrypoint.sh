#!/bin/sh
set -e

# Применяем миграции
echo "Applying migrations..."
python manage.py migrate --noinput

# Собираем статические файлы
echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

# Проверка статических файлов
echo "Checking static files..."
if [ -d "staticfiles/admin" ]; then
    echo "✅ Admin static files found"
    echo "Admin static files:"
    ls -la staticfiles/admin/css/ | head -5
else
    echo "❌ Admin static files not found"
fi

# Создаём суперпользователя, если его нет
DJANGO_SUPERUSER_USERNAME=${DJANGO_SUPERUSER_USERNAME:-admin}
DJANGO_SUPERUSER_PASSWORD=${DJANGO_SUPERUSER_PASSWORD:-defaultpass}
DJANGO_SUPERUSER_EMAIL=${DJANGO_SUPERUSER_EMAIL:-admin@example.com}

# Проверяем, существует ли пользователь через manage.py
echo "Checking if superuser $DJANGO_SUPERUSER_USERNAME exists..."
if ! python manage.py shell -c "from django.contrib.auth import get_user_model; print('EXISTS:', get_user_model().objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists())" 2>/dev/null | grep -q "EXISTS: True"; then
  echo "Creating superuser $DJANGO_SUPERUSER_USERNAME..."
  python manage.py createsuperuser --noinput \
    --username "$DJANGO_SUPERUSER_USERNAME" \
    --email "$DJANGO_SUPERUSER_EMAIL"

  # Установка пароля через Django shell
  python manage.py shell -c "
from django.contrib.auth import get_user_model
user = get_user_model().objects.get(username='$DJANGO_SUPERUSER_USERNAME')
user.set_password('$DJANGO_SUPERUSER_PASSWORD')
user.save()
print('Password set for', user.username)
"
else
  echo "Superuser $DJANGO_SUPERUSER_USERNAME already exists."
fi

# Запуск приложения
exec granian --interface asgi DiplomNetologyGjango.asgi:application --host 0.0.0.0 --port 8000