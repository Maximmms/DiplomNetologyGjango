from __future__ import annotations

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from backend.models import (
    Category,
    ConfirmationToken,
    Contact,
    Order,
    OrderItem,
    Parameter,
    Phone,
    Product,
    ProductInfo,
    ProductParameter,
    Shop,
    User,
)


class OrderItemInline(admin.StackedInline):
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


class UserPhoneInline(admin.StackedInline):
    model = Phone
    extra = 0
    verbose_name = "Телефон"
    verbose_name_plural = "Телефоны"


class OrderInline(admin.StackedInline):
    model = Order
    extra = 0
    verbose_name = _("Заказ")
    verbose_name_plural = _("Заказы")
    fields = ("dt", "status")
    readonly_fields = ["dt"]


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "first_name", "last_name", "is_staff")
    search_fields = ("email", "first_name", "last_name")
    list_filter = ("is_active", "type")
    ordering = ("email",)
    inlines = [ContactInline, UserPhoneInline, OrderInline]
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
    def get_phone(self, obj):
        return obj.user_phone.phone_number if hasattr(obj, "user_phone") else None

    get_phone.short_description = "Телефон"


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ("name", "url", "user", "state")
    search_fields = ("name", "url", "state")
    inlines = [ProductInfoInlineForShop]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "all_parameters")
    search_fields = ("name",)
    inlines = [ProductInfoInline]

    def all_parameters(self, obj):
        return ", ".join(
            f"{pp.parameter.name}: {pp.value}"
            for product_info in obj.product_infos.all()
            for pp in product_info.parameters.all()
        )

    all_parameters.short_description = "Характеристики"


@admin.register(ProductInfo)
class ProductInfoAdmin(admin.ModelAdmin):
    list_display = ("product", "model", "external_id","shop", "price", "price_rrc", "quantity")
    search_fields = ("product__name", "shop__name", "model", "external_id")


@admin.register(Parameter)
class ParameterAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(ProductParameter)
class ProductParameterAdmin(admin.ModelAdmin):
    list_display = ("product_info", "parameter", "value")
    search_fields = ("parameter__name",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("user", "dt", "status")
    search_fields = ("user__email", "status")
    list_filter = ("dt", "status")
    inlines = [OrderItemInline]
    readonly_fields = ["dt"]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product_name", "shop_name", "quantity")

    def product_name(self, obj):
        return obj.product_info.product.name

    def shop_name(self, obj):
        return obj.product_info.shop.name

    product_name.short_description = "Продукт"
    shop_name.short_description = "Магазин"


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "zipcode",
        "city",
        "street",
        "building",
        "appartment",
        "user_email",
        "formatted_phone"
    )
    list_filter = ("zipcode", "city", "street", "building", "appartment")
    search_fields = ("user__email",)
    ordering = ("user",)

    def user_email(self, obj):
        return obj.user.email if obj.user else None

    def formatted_phone(self, obj):
        if obj.phone_number:
            return (f"+{obj.phone_number[:1]} "
                    f"({obj.phone_number[1:4]}) "
                    f"{obj.phone_number[4:7]}"
                    f"-{obj.phone_number[7:9]}"
                    f"-{obj.phone_number[9:]}")
        return ""

    user_email.short_description = "Email пользователя"
    formatted_phone.short_description = "Номер телефона"


@admin.register(ConfirmationToken)
class ConfirmationTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "key", "expires_at")
