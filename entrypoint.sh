#!/bin/sh
set -e

# Применяем миграции
echo "Applying migrations..."
python manage.py makemigrations
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
DJANGO_SUPERUSER_PASSWORD=${DJANGO_SUPERUSER_PASSWORD:-defaultpass}
DJANGO_SUPERUSER_EMAIL=${DJANGO_SUPERUSER_EMAIL:-admin@example.com}

echo "Checking if superuser $DJANGO_SUPERUSER_EMAIL exists..."
if ! python manage.py shell -c "from backend.models import User; print('EXISTS:', User.objects.filter(email='$DJANGO_SUPERUSER_EMAIL').exists())" 2>/dev/null | grep -q "EXISTS: True"; then
  echo "Creating superuser $DJANGO_SUPERUSER_EMAIL..."

  # Создаем суперпользователя через Django shell с правильными параметрами
  python manage.py shell -c "
from backend.models import User
try:
    user = User.objects.create_superuser(
        email='$DJANGO_SUPERUSER_EMAIL',
        username='$DJANGO_SUPERUSER_USERNAME',
        password='$DJANGO_SUPERUSER_PASSWORD',
        is_active=True
    )
    print('✅ Superuser created successfully:', user.email)
except Exception as e:
    print('❌ Error creating superuser:', str(e))
"
else
  echo "Superuser $DJANGO_SUPERUSER_EMAIL already exists."

  # Обновляем пароль на случай, если он изменился
  python manage.py shell -c "
from backend.models import User
try:
    user = User.objects.get(email='$DJANGO_SUPERUSER_EMAIL')
    user = User.objects.get(username='$DJANGO_SUPERUSER_USERNAME')
    user.set_password('$DJANGO_SUPERUSER_PASSWORD')
    user.is_active = True
    user.save()
    print('✅ Password updated for:', user.email)
except Exception as e:
    print('❌ Error updating user:', str(e))
"
fi

# Запуск приложения
exec granian --interface asgi DiplomNetologyGjango.asgi:application --host 0.0.0.0 --port 8000