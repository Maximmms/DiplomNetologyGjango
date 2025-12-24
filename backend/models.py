from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import jwt
from autoslug import AutoSlugField
from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser, PermissionsMixin
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

UNITS_OF_MEASURE = [
    # 📏 Длина
    ("m", "метр"),
    ("cm", "сантиметр"),
    ("mm", "миллиметр"),

    # ⏲️ Время
    ("s", "секунда"),
    ("min", "минута"),
    ("h", "час"),

    # ⚖️ Масса
    ("kg", "килограмм"),
    ("g", "грамм"),
    ("mg", "миллиграмм"),

    # 📦 Объём
    ("l", "литр"),
    ("ml", "миллилитр"),

    # 🔢 Штуки и упаковки
    ("pcs", "штука"),
    ("set", "набор"),
    ("pkg", "упаковка"),
    ("roll", "рулон"),
    ("pair", "пара"),
    ("box", "коробка"),

    # 🖼️ Площадь
    ("m2", "кв. метр"),
    ("cm2", "кв. сантиметр"),
    ("m2", "кв. метр"),

    # 🔋 Электричество
    ("Ah", "ампер-час"),
    ("mAh", "миллиампер-час"),
    ("kWh", "киловатт-час"),

    # 📈 Прочие
    ("%", "процент"),
    ("dB", "децибел"),
    ("dpi", "точек на дюйм"),
    ("px", "пиксель"),
    ("ppi", "пикселей на дюйм"),
    ("Hz", "герц"),
    ("kHz", "килогерц"),
    ("MHz", "мегагерц"),
    ("GHz", "гигагерц"),
    ("W", "ватт"),
    ("kW", "киловатт"),
    ("V", "вольт"),
    ("A", "ампер"),
    ("Ω", "ом"),
]


class UserManager(BaseUserManager):
    """
    Миксин для управления пользователями
    """
    use_in_migrations = True

    def _create_user(self, username, email, password, **extra_fields):
        """
        Create and save a user with the given username, email, and password.
        """
        if not username:
            raise ValueError("Указанное имя пользователя должно быть установлено")

        if not email:
            raise ValueError("Данный адрес электронной почты должен быть установлен")
        email = self.normalize_email(email)
        user = self.model(username = username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, email, password=None, **extra_fields):
        """
        Создает и возвращает `User` с адресом электронной почты,
        именем пользователя и паролем.
        """
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email, password, **extra_fields):
        """
        Создает и возвращает пользователя с правами
        суперпользователя (администратора).
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if not (
            extra_fields.get("is_staff", False)
            and extra_fields.get("is_superuser", False)
        ):
            raise ValueError("Суперпользователь должен иметь is_staff=True и is_superuser=True.")

        return self._create_user(username, email, password, **extra_fields)

    def get_by_natural_key(self, email):
        """
        Позволяет аутентифицироваться по email.
        Вызывается при authenticate(email='...')
        """
        return self.get(email=email)


class User(AbstractUser, PermissionsMixin):
    """
    Стандартная модель пользователей
    """
    USER_TYPE_CHOICES = (
        ("buyer", "Покупатель"),
        ("shop", "Магазин"),
    )

    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ("username",)
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
    phone_number = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name="Номер телефона"
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
        max_length=10,
        default="buyer",
    )

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def token(self):
        """
        Позволяет нам получить токен пользователя, вызвав `user.token` вместо
        `user.generate_jwt_token().
        """
        return self._generate_jwt_token()


    def _generate_jwt_token(self):
        """
        Создает веб-токен JSON, в котором хранится идентификатор
        этого пользователя и срок его действия
        составляет 60 дней в будущем.
        """
        dt = datetime.now() + timedelta(days=60)

        token = jwt.encode({
            "id": self.pk,
            "exp": int(dt.strftime("%s"))
        }, settings.SECRET_KEY, algorithm="HS256")

        return token.decode("utf-8")

    class Meta:
        db_table = "backend_user"
        verbose_name = "Пользователь"
        verbose_name_plural = "Список пользователей"
        ordering = ("email",)


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
        verbose_name="Почтовый индекс"
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
        verbose_name="Номер дома"
    )
    appartment = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name="Номер квартиры"
    )


    def __str__(self):
        return f"{self.user} - {self.zipcode} {self.city} {self.street} {self.building} {self.appartment} "

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
            models.UniqueConstraint(fields=["user"], name="unique_user_address")
        ]


class Shop(models.Model):
    url = models.URLField(verbose_name="Сайт магазина", null=True, blank=True)
    name = models.CharField(max_length=255, verbose_name="Название магазина")
    slug = AutoSlugField(
        populate_from="name",
        unique=True,
        always_update=False,
        max_length=120,
        verbose_name="Slug",
        help_text="Уникальный идентификатор URL (генерируется автоматически)",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name="Владелец магазина",
        blank=True,
        null=True,
        related_name="shops",
    )
    state = models.BooleanField(verbose_name="Прием заказов", default=True)

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
        verbose_name="Категория",
        related_name="products"
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
    product = models.ForeignKey(
        Product,
        related_name="product_infos",
        on_delete=models.CASCADE,
        verbose_name="Продукт"
    )
    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="products",
        verbose_name="Поставщик"
    )
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
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        default=0,
        verbose_name="Доступное количество"
    )
    unit_of_measure = models.CharField(
        max_length=10,
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
        indexes = [models.Index(fields=["parameter", "value"])]
        constraints = [
        models.UniqueConstraint(
        fields=["product_info", "parameter"],
        name="unique_product_parameter"
        ),
        ]


class Order(models.Model):
    ORDER_STATUS_CHOICES = (
        ("basket", "Статус корзины"),
        ("new", "Новый"),
        ("confirmed", "Подтвержден"),
        ("assembled", "Собран"),
        ("sent", "Отправлен"),
        ("delivered", "Доставлен"),
        ("canceled", "Отменен"),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="orders"
    )
    dt = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата"
    )
    delivery_address = models.ForeignKey(Contact, on_delete=models.CASCADE, null=True)
    status = models.CharField(
        max_length=16,
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
    ORDER_ITEM_STATUS_CHOICES = [
        ("pending", "Ожидает подтверждения"),
        ("confirmed", "Подтверждено"),
        ("rejected", "Отменено поставщиком"),
    ]

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="items", verbose_name="Заказ"
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
    shop_confirmed = models.BooleanField(
        default=False,
        verbose_name="Подтвержден поставщиком",
        help_text="Указывает, что поставщик подтвердил наличие и готовность собрать товар"
    )
    status = models.CharField(
        max_length=20,
        choices=ORDER_ITEM_STATUS_CHOICES,
        default="pending",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.product_info.product} - {self.quantity} - {self.get_status_display()}"

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


class OrderHistory(models.Model):
    ACTION_CHOICES = [
        ("status_updated", "Статус изменён"),
        ("item_rejected", "Товар отменён поставщиком"),
        ("item_confirmed", "Товар подтверждён"),
        ("order_assembled", "Заказ собран"),
        ("order_canceled", "Заказ отменён"),
        ("partner_action", "Действие партнёра"),
    ]

    order = models.ForeignKey(
        "Order",
        on_delete=models.CASCADE,
        related_name="order_history",
        verbose_name="Заказ"
    )
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        verbose_name="Действие"
    )
    details = models.JSONField(
        blank=True,
        null=True,
        verbose_name="Детали (JSON)"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Пользователь"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата и время"
    )

    class Meta:
        verbose_name = "История заказа"
        verbose_name_plural = "История заказов"
        ordering = ["-created_at",]

    def __str__(self):
        return f"{self.get_action_display()} — {self.order.id} — {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class AdminActionLog(models.Model):
    ACTION_CHOICES = [
        ("order_status_change", "Изменение статуса заказа"),
        ("price_upload", "Загрузка прайс-листа"),
        ("order_item_update", "Изменение позиции заказа"),
        ("other", "Другое действие"),
    ]

    action = models.CharField("Действие", max_length=50, choices=ACTION_CHOICES)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Пользователь")
    details = models.JSONField("Детали", help_text="Например: order_id=5, old_status=new, new_status=confirmed")
    ip_address = models.GenericIPAddressField("IP-адрес", blank=True, null=True)
    user_agent = models.TextField("User-Agent", blank=True)
    timestamp = models.DateTimeField("Время", default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "Аудит администратора"
        verbose_name_plural = "Аудит действий администраторов"
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.get_action_display()} — {self.user} — {self.timestamp}"

class EmailConfirmation(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="email_confirmations",
    )
    code = models.CharField(max_length=12)
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )
    is_verified = models.BooleanField(
        default=False,
        verbose_name="Подтвержден"
    )

    def __str__(self):
        return f"{self.user.email} - {self.code}"


class DailySalesReport(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE)
    date = models.DateField()
    total_sales = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    order_count = models.IntegerField(default=0)

    class Meta:
        unique_together = ('shop', 'date')


class EmailChangeRequest(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="email_change_request")
    new_email = models.EmailField(unique=True)
    code = models.CharField(max_length=12)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.email} → {self.new_email}"