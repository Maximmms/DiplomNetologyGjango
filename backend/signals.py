from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save
from django.dispatch import receiver

from backend.models import Contact


@receiver(pre_save, sender=Contact)
def limit_contacts(sender, instance, **kwargs):
    if instance.pk:
        # Обновление: исключаем текущий контакт
        filter_kwargs = {"user": instance.user, "pk__ne": instance.pk}
    else:
        # Создание: не исключаем ничего
        filter_kwargs = {"user": instance.user}

    count = Contact.objects.filter(**filter_kwargs).count()
    if count >= 5:
        raise ValidationError("Вы не можете добавить больше 5 контактов.")
