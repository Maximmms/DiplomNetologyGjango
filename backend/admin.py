from __future__ import annotations

from django import forms
from django.contrib import admin
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.utils.translation import gettext_lazy as _

from backend.models import (
    Category,
    Contact,
    Order,
    OrderItem,
    Parameter,
    Product,
    ProductInfo,
    ProductParameter,
    Shop,
    User,
)
from backend.utils import normalize_phone_number


class UserAdminForm(forms.ModelForm):
    phone_number = forms.CharField(
        label="Телефон",
        required=False,
        max_length=20,
        help_text="Формат: +7 999 999-99-99"
    )

    class Meta:
        model = User
        fields = [
            "email",
            "password",
            "first_name",
            "last_name",
            "company",
            "position",
            "phone_number",
            "type",
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
            "last_login",
            "date_joined",
        ]

    def clean_phone_number(self):
        raw_number = self.cleaned_data.get("phone_number")
        if raw_number:
            cleaned_digits = "".join(filter(str.isdigit, raw_number))
            if len(cleaned_digits) > 20:
                raise ValidationError("Номер слишком длинный.")
            # Нормализуем через утилиту
            return normalize_phone_number(raw_number)
        return raw_number

    def save(self, commit=True):
        user = super().save(commit=False)
        # Убедимся, что нормализованный номер сохранится
        user.phone_number = self.cleaned_data["phone_number"]
        if commit:
            user.save()
        return user


class ContactForm(forms.ModelForm):
    phone_number = forms.CharField(
        label="Телефон",
        required=False,
        max_length=20,
        help_text="Формат: +7 999 999-99-99"
    )

    class Meta:
        model = Contact
        fields = [
            "user",
            "zipcode",
            "city",
            "street",
            "building",
            "appartment",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Заполняем поле phone_number текущим значением из User
        try:
            if self.instance and self.instance.user:
                self.fields["phone_number"].initial = self.instance.user.phone_number
        except ObjectDoesNotExist:
            # user был удалён, но контакт остался
            pass
        except AttributeError:
            # user — не существует как атрибут
            pass

    def clean_phone_number(self):
        raw_number = self.cleaned_data.get("phone_number")
        if raw_number:
            # Валидация длины
            cleaned_digits = "".join(filter(str.isdigit, raw_number))
            if len(cleaned_digits) > 20:
                raise ValidationError("Номер слишком длинный.")
            # Нормализуем
            return normalize_phone_number(raw_number)
        return raw_number

    def save(self, commit=True):
        contact = super().save(commit=False)
        normalized_phone = self.cleaned_data.get("phone_number")  # уже нормализован

        user = contact.user

        if commit:
            contact.save()

        if user and user.phone_number != normalized_phone:
            user.phone_number = normalized_phone
            user.save(update_fields=["phone_number"])

        return contact


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    verbose_name = _("Позиция заказа")
    verbose_name_plural = _("Позиции заказа")
    fields = ("product_info", "quantity")
    autocomplete_fields = ("product_info",)


class ProductParameterInline(admin.StackedInline):
    model = ProductParameter
    extra = 0
    verbose_name = _("Характеристика продукта")
    verbose_name_plural = _("Характеристики продукта")
    fields = ("parameter", "value")
    autocomplete_fields = ("parameter",)


class ProductInfoInline(admin.StackedInline):
    model = ProductInfo
    extra = 0
    verbose_name = _("Информация о продукте")
    verbose_name_plural = _("Информация о продуктах")
    fields = ("shop", "price", "price_rrc", "quantity")
    inlines = [ProductParameterInline]


class ProductInfoInlineForShop(admin.StackedInline):
    model = ProductInfo
    extra = 0
    verbose_name = _("Информация о продукте")
    verbose_name_plural = _("Информация о продуктах")
    fields = ("product", "price", "price_rrc", "quantity")


class ContactInline(admin.StackedInline):
    model = Contact
    extra = 0
    verbose_name = _("Контакт")
    verbose_name_plural = _("Контакты")
    fields = ("zipcode", "city", "street", "building", "appartment")

    def get_max_num(self, request, obj=None, **kwargs):
        return 5 # Максимум 5 записей


class OrderInline(admin.StackedInline):
    model = Order
    extra = 0
    verbose_name = _("Заказ")
    verbose_name_plural = _("Заказы")
    fields = ("dt", "status")
    readonly_fields = ["dt"]


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    form = UserAdminForm
    list_display = (
        "email", "first_name", "last_name",
        "formatted_phone", "is_active", "is_staff"
    )
    search_fields = ("email", "first_name", "last_name")
    list_filter = ("is_active", "type")
    ordering = ("email",)
    inlines = [ContactInline,  OrderInline]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            _("Personal info"),
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "company",
                    "username",
                    "position",
                    "phone_number",
                    "type",
                )
            },
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    def formatted_phone(self, obj):
        phone = obj.phone_number
        if phone and phone.startswith("+7") and len(phone) == 12:
            number = phone[1:]  # убираем +
            return f"{number[0]} ({number[1:4]}) {number[4:7]}-{number[7:9]}-{number[9:]}"
        return phone or ""

    formatted_phone.short_description = "Телефон (форматированный)"


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ("name", "url", "user", "state")
    search_fields = ("name", "url", "state")
    inlines = [ProductInfoInlineForShop]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "shop_list")
    search_fields = ("name",)

    def shop_list(self, obj):
        return ", ".join(str(shop) for shop in obj.shops.all())

    shop_list.short_description = "Магазины"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "all_parameters")
    search_fields = ("name",)
    inlines = [ProductInfoInline]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            "product_infos__parameters"
        )

    def all_parameters(self, obj):
        if not hasattr(obj, "product_infos"):
            return ""
        parameters = []
        for product_info in obj.product_infos.all():
            for pp in product_info.parameters.all():
                parameters.append(f"{pp.parameter.name}: {pp.value}")
        return ", ".join(parameters)

    all_parameters.short_description = "Характеристики"


@admin.register(ProductInfo)
class ProductInfoAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "model",
        "external_id",
        "price",
        "price_rrc",
        "quantity",
        "shop"
    )
    search_fields = ("product__name", "shop__name", "model", "external_id")

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("parameters")


@admin.register(Parameter)
class ParameterAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            "productparameter_set"
        )


@admin.register(ProductParameter)
class ProductParameterAdmin(admin.ModelAdmin):
    list_display = ("product_info", "parameter", "value")
    search_fields = ("parameter__name",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "product_info", "parameter"
        )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("user", "dt", "status")
    search_fields = ("user__email", "status")
    list_filter = ("dt", "status")
    inlines = [OrderItemInline]
    readonly_fields = ["dt"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "user"
        ).prefetch_related(
            "orderitem_set"
        )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product_name", "shop_name", "quantity")

    def product_name(self, obj):
        return obj.product_info.product.name

    def shop_name(self, obj):
        return obj.product_info.shop.name

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            "product_info__product",
            "product_info__shop",
        )

    product_name.short_description = "Продукт"
    shop_name.short_description = "Магазин"


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    form = ContactForm
    list_display = (
        "user",
        "zipcode",
        "city",
        "street",
        "building",
        "appartment",
        "user_email",
        "formatted_phone",
    )
    list_filter = ("zipcode", "city", "street", "building", "appartment")
    search_fields = ("user__email",)
    ordering = ("user",)

    def user_email(self, obj):
        return obj.user.email if obj.user else None

    def formatted_phone(self, obj):
        user = obj.user
        if user and user.phone_number:
            number = user.phone_number
            # Проверим формат: +7XXXXXXXXXX
            if number.startswith("+7") and len(number) == 12:
                n = number[1:]
                return f"+{n[0]} ({n[1:4]}) {n[4:7]}-{n[7:9]}-{n[9:]}"
        return ""

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "user"
        ).prefetch_related(
            "user__user_phone"
        )

    user_email.short_description = "Email пользователя"
    formatted_phone.short_description = "Номер телефона"