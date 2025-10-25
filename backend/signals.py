from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save
from django.dispatch import receiver

from backend.models import Contact


@receiver(pre_save, sender =Contact)
def limit_contacts(sender, instance, **kwargs):
    # Проверяем, сколько уже существует контактов у этого пользователя
    if Contact.objects.filter(user=instance.user).exclude(pk=instance.pk).count() >= 5:
        raise ValidationError("Вы не можете добавить больше 5 контактов.")
