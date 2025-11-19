from __future__ import annotations

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from backend.models import (
    Contact,
    User,
)


@receiver(pre_save, sender=Contact)
def limit_contacts(sender, instance, **kwargs):
    """
    Ограничивает количество контактов:
    - Обычные пользователи могут иметь до 5 контактов.
    - Пользователи из группы "Магазины" (тип 'shop') — только 1 контакт.
    """
    try:
        shop_group = Group.objects.get(name="Магазины")
    except Group.DoesNotExist:
        return

    is_shop_user = instance.user.type == "shop" or (
        instance.user.pk and shop_group in instance.user.groups.all()
    )

    filter_kwargs = {"user": instance.user}

    if instance.pk:
        filter_kwargs["pk"] = instance.pk

    count = Contact.objects.filter(**filter_kwargs).count()

    if is_shop_user and count >= 1:
        raise ValidationError("У магазина может быть только один адрес.")
    elif count >= 5:
        raise ValidationError("Вы не можете добавить больше 5 контактов.")



@receiver(post_save, sender=User)
def add_user_to_shop_group(sender, instance, created, **kwargs):
    """
    Автоматически добавляет пользователя в группу "Магазины",
    если его тип — 'shop'. Убирает из группы, если тип изменён.
    """
    try:
        shop_group = Group.objects.get(name="Магазины")
    except Group.DoesNotExist:
        # Группа будет создана позже через post_migrate
        return

    if instance.type == "shop":
        instance.groups.add(shop_group)
    else:
        instance.groups.remove(shop_group)
