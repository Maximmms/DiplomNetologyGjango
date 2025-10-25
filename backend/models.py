from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

USER_TYPE_CHOICES = (
    ("buyer", "Покупатель"),
    ("shop", "Магазин"),
)

ORDER_STATUS_CHOICES = (
    ("basket", "Статус корзины"),
    ("new", "Новый"),
    ("confirmed", "Подтвержден"),
    ("assembled", "Собран"),
    ("sent", "Отправлен"),
    ("delivered", "Доставлен"),
    ("canceled", "Отменен"),
)

UNITS_OF_MEASURE = [
    ("pcs", "Штука"),
    ("kg", "Килограмм"),
    ("l", "Литр"),
    ("pkg", "Упаковка"),
    ("g", "Грамм"),
    ("ml", "Миллилитр"),
    ("m", "Метр"),
]


class UserManager(BaseUserManager):
    """
    Миксин для управления пользователями
    """
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        """
        Create and save a user with the given username, email, and password.
        """
        if not email:
            raise ValueError("The given email must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Стандартная модель пользователей
    """
    REQUIRED_FIELDS = []
    objects = UserManager()
    USERNAME_FIELD = "email"
    email = models.EmailField(
        verbose_name="Электронная почта",
        unique=True
    )
    first_name = models.CharField(
        verbose_name="Имя",
        max_length=40,
    )
    last_name = models.CharField(
        verbose_name="Фамилия",
        max_length=40,
    )
    company = models.CharField(
        verbose_name="Компания",
        max_length=40,
        blank=True
    )
    position = models.CharField(
        verbose_name="Должность",
        max_length=40,
        blank=True
    )
    username_validator = UnicodeUsernameValidator()
    username = models.CharField(
        max_length=150,
        verbose_name = "Имя пользователя",
        help_text=_("Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only."),
        validators=[username_validator],
        error_messages={
            "unique": _("A user with that username already exists."),
        },
    )
    is_active = models.BooleanField(
        _("active"),
        default=False,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )
    type = models.CharField(
        verbose_name="Тип пользователя",
        choices=USER_TYPE_CHOICES,
        max_length=5,
        default="buyer"
    )

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    class Meta:
        db_table = "backend_user"
        verbose_name = "Пользователь"
        verbose_name_plural = "Список пользователей"
        ordering = ("email",)


class Shop(models.Model):
    url = models.URLField(
        verbose_name="Сайт магазина",
        null=True,
        blank=True
    )
    name = models.CharField(
        max_length=255,
        verbose_name="Название магазина"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name="Владелец магазина",
        blank=True,
        null=True,
        related_name="shops",
    )
    state = models.BooleanField(
        verbose_name="Прием заказов",
        default=True
    )

    def __str__(self):
        return self.name or self.url or "Без названия"

    class Meta:
        verbose_name = "Магазин"
        verbose_name_plural = "Магазины"


class Category(models.Model):
    shops = models.ManyToManyField(
        Shop,
        related_name="categories",
        verbose_name="Магазины"
    )
    name = models.CharField(
        max_length=255,
        verbose_name="Название категории"
    )

    def __str__(self):
        return self.name or "Без категории"

    class Meta:
        verbose_name = "Категория товара"
        verbose_name_plural = "Категории товара"


class Product(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        verbose_name="Категория"
    )
    name = models.CharField(
        max_length=255,
        verbose_name="Название товара"
    )

    def __str__(self):
        return self.name or "Без названия"

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"


class ProductInfo(models.Model):
    objects = models.manager.Manager()
    model = models.CharField(
        max_length=50,
        verbose_name="Модель товара",
        blank=True
        )
    external_id = models.CharField(
        max_length=50,
        verbose_name="Внешний идентификатор",
        blank=True
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        verbose_name="Продукт"
    )
    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="products",
        verbose_name="Поставщик"
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        default=0,
        verbose_name="Доступное количество"
    )
    unit_of_measure = models.CharField(
        max_length=5,
        choices=UNITS_OF_MEASURE,
        default="pcs",
        verbose_name="Единица измерения"
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Цена поставщика"
    )
    price_rrc = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Рекомендованная розничная цена (РРЦ)"
    )

    def __str__(self):
        return f"{self.product} ({self.shop.name})"

    def format_price(self):
        return f"{self.price:.2f} руб."

    def format_price_rrc(self):
        return f"{self.price_rrc:.2f} руб."

    class Meta:
        verbose_name = "Информация о товаре в магазине"
        verbose_name_plural = "Информация о товарах в магазинах"
        indexes = [
            models.Index(fields=["product", "shop"])
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "shop", "external_id"],
                name="unique_product_info"
            ),
        ]


class Parameter(models.Model):
    name = models.CharField(
        max_length=30,
        verbose_name="Название параметра"
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Параметр товара"
        verbose_name_plural = "Параметры товаров"
        ordering = ("-name",)


class ProductParameter(models.Model):
    product_info = models.ForeignKey(
        ProductInfo,
        on_delete=models.CASCADE,
        related_name="parameters"
    )
    parameter = models.ForeignKey(
        Parameter,
        on_delete=models.CASCADE
    )
    value = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.parameter} - {self.value}"

    class Meta:
        verbose_name = "Параметр товара"
        verbose_name_plural = "Список параметров товара"
        indexes = [
            models.Index(
                fields=["parameter", "value"]
            )
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["product_info", "parameter"],
                name="unique_product_parameter"
            ),
        ]


class Order(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="orders"
    )
    dt = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата"
    )
    status = models.CharField(
        max_length=255,
        default="new",
        choices=ORDER_STATUS_CHOICES,
        verbose_name="Статус заказа"
    )

    def __str__(self):
        return self.dt.strftime("%Y-%m-%d %H:%M") if self.dt else "Без даты"

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        indexes = [
            models.Index(
                fields=["user", "status"]
            )
        ]
        ordering = ("-dt",)


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Заказ"
    )
    product_info = models.ForeignKey(
        ProductInfo,
        on_delete=models.CASCADE,
        related_name="order_items",
        verbose_name="Товар"
    )
    quantity = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество"
    )

    def __str__(self):
        return f"{self.product_info.product} - {self.quantity}"

    class Meta:
        verbose_name = "Пункт заказа"
        verbose_name_plural = "Пункты заказа"
        indexes = [models.Index(fields=["order", "product_info"])]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "product_info"],
                name="unique_order_item"
            )
        ]


class Phone(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="user_phone",
        verbose_name="Пользователь"
    )
    phone_number = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name="Номер телефона"
        )

    class Meta:
        verbose_name = "Телефон пользователя"
        verbose_name_plural = "Телефоны пользователей"


class Contact(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="user_contacts",
        verbose_name="Пользователь"
    )
    zipcode = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name="Почтоывй индекс"
    )
    city = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="Город"
    )
    street = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Улица"
    )
    building = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name="Ноемр дома"
    )
    appartment = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name="Номер квартиры"
    )


    def __str__(self):
        return f"{self.user} - {self.zipcode} {self.city} {self.street} {self.building} {self.appartment}"

    def save(self, *args, **kwargs):
        if Contact.objects.filter(user=self.user).count() >= 5:
            raise ValueError(
                "Пользователь может иметь не более 5 адресов"
            )
        else:
            return super().save(*args, **kwargs)


    class Meta:
        verbose_name = "Контактная информация пользователя"
        verbose_name_plural = "Контактные данные пользователей"
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                name="unique_user_address"
            )
        ]


class ConfirmationToken(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="confirmation_tokens",
        verbose_name="Пользователь",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
        help_text="Дата создания токена",
    )
    expires_at = models.DateTimeField(
        verbose_name="Дата истечения",
        help_text="Дата истечения токена",
        null=True,
    )
    key = models.CharField(
        _("Key"),
        max_length=64,
        db_index=True,
        unique=True
    )

    @staticmethod
    def generate_key():
        return str(uuid.uuid4()).replace("-", "")

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=14)
        return super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"Password reset token for user {self.user}"

    class Meta:
        verbose_name = "Токен подтверждения"
        verbose_name_plural = "Токены подтверждения"
