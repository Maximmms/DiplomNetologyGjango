from __future__ import annotations

from django.core.management import BaseCommand
from django.utils import timezone

from backend.models import ConfirmationToken


class Command(BaseCommand):
    help = "Удаление просроченных токенов"

    def handle(self, *args, **options):
        expired_tokens = ConfirmationToken.objects.filter(expires_at__lt=timezone.now())
        count = expired_tokens.count()
        expired_tokens.delete()
        self.stdout.write(self.style.SUCCESS(f"Удалено {count} просроченных токенов"))
