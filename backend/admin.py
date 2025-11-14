from __future__ import annotations

import yaml
from django import forms
from django.contrib import admin, messages
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.html import format_html
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
from backend.tasks import process_shop_data_async
from backend.utils.normalizers import normalize_phone_number


class UploadYAMLForm(forms.Form):
    yaml_file = forms.FileField(
        label=_("YAML файл"),
        help_text=_("Загрузите YAML-файл с данными о товарах."),
        widget=forms.FileInput(attrs={"accept": ".yaml,.yml"})
    )

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
            return normalize_phone_number(raw_number)
        return raw_number

    def save(self, commit=True):
        user = super().save(commit=False)
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
        try:
            if self.instance and self.instance.user:
                self.fields["phone_number"].initial = self.instance.user.phone_number
        except ObjectDoesNotExist:
            pass
        except AttributeError:
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

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("product_info__product", "product_info__shop")
        if request.user.is_superuser:
            return qs
        if request.user.groups.filter(name="Магазины").exists():
            user_shops = request.user.shops.all()
            if not user_shops.exists():
                return qs.none()
            return qs.filter(product_info__shop__in=user_shops)
        return qs

    def has_change_permission(self, request, obj=None):
        if request.user.groups.filter(name="Магазины").exists():
            if obj is not None and hasattr(obj, "product_info"):
                return obj.product_info.shop in request.user.shops.all()
            return True
        return super().has_change_permission(request, obj)


class ProductParameterInline(admin.StackedInline):
    model = ProductParameter
    extra = 0
    verbose_name = _("Характеристика продукта")
    verbose_name_plural = _("Характеристики продукта")
    fields = ("parameter", "value")
    autocomplete_fields = ("parameter",)

    def has_add_permission(self, request, obj):
        if request.user.groups.filter(name="Магазины").exists():
            return True
        return super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if request.user.groups.filter(name="Магазины").exists():
            if obj and obj.product_info.shop in request.user.shops.all():
                return True
            return False
        return super().has_change_permission(request, obj)


class ProductInfoInline(admin.StackedInline):
    model = ProductInfo
    extra = 1
    max_num = 1
    verbose_name = _("Информация о продукте")
    verbose_name_plural = _("Информация о продуктах")
    fields = ("shop", "price", "price_rrc", "quantity")
    inlines = [ProductParameterInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("shop")
        if request.user.is_superuser:
            return qs
        if request.user.groups.filter(name="Магазины").exists():
            user_shops = request.user.shops.all()
            if not user_shops.exists():
                return qs.none()
            return qs.filter(shop__in=user_shops)
        return qs

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "shop" and request.user.groups.filter(name="Магазины").exists():
            kwargs["queryset"] = request.user.shops.all()
            kwargs["initial"] = request.user.shops.first()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ["shop"]
        return []

    def has_add_permission(self, request, obj):
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name="Магазины").exists():
            return True
        return super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name="Магазины").exists():
            if obj is not None:
                return obj.shop in request.user.shops.all()
            return True
        return super().has_change_permission(request, obj)


class ProductInfoInlineForShop(admin.StackedInline):
    model = ProductInfo
    extra = 0
    verbose_name = _("Информация о продукте")
    verbose_name_plural = _("Информация о продуктах")
    fields = ("product", "price", "price_rrc", "quantity")


class ContactInline(admin.StackedInline):
    model = Contact
    extra = 0
    max_num = 1
    verbose_name = _("Контакт")
    verbose_name_plural = _("Контакты")
    fields = ("zipcode", "city", "street", "building", "appartment")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if request.user.groups.filter(name="Магазины").exists():
            return qs.filter(user=request.user)
        return qs

    def has_add_permission(self, request, obj):
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name="Магазины").exists():
            # Запрещаем добавлять, если уже есть контакт
            return not Contact.objects.filter(user=request.user).exists()
        return super().has_add_permission(request, obj)


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
        "email",
        "first_name",
        "last_name",
        "formatted_phone",
        "is_active",
        "is_staff",
    )
    search_fields = ("email", "first_name", "last_name")
    list_filter = ("is_active", "type")
    ordering = ("email",)

    def get_inlines(self, request, obj=None):
        inlines = [OrderInline]
        if not request.user.groups.filter(name="Магазины").exists():
            inlines.append(ContactInline)
        else:
            if obj and obj == request.user:
                inlines.append(ContactInline)
        return inlines

    def get_fieldsets(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name="Магазины").exists():
            return (
                (None, {"fields": ("email",)}),
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
                        )
                    },
                ),
            )
        else:
            return (
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

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if request.user.groups.filter(name="Магазины").exists():
            return qs.filter(pk=request.user.pk)
        return qs

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name="Магазины").exists():
            if obj is not None:
                return obj.pk == request.user.pk
            return False
        return super().has_change_permission(request, obj)

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name="Магазины").exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name="Магазины").exists():
            if obj is not None:
                return obj.pk == request.user.pk
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ("name", "url", "user", "state", "import_yaml_button")
    search_fields = ("name", "url", "state")
    inlines = [ProductInfoInlineForShop]
    readonly_fields = ["user"]

    def get_urls(self):
        urls = super().get_urls()
        from django.urls import path
        custom_urls = [
            path(
                "<int:shop_id>/upload-yaml/",
                self.admin_site.admin_view(self.upload_yaml_view),
                name="shop_upload_yaml",
            ),
        ]
        return custom_urls + urls

    def import_yaml_button(self, obj):
        url = reverse("admin:shop_upload_yaml", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}">Загрузить YAML</a>',
            url
        )

    import_yaml_button.short_description = "Загрузка YAML"
    import_yaml_button.allow_tags = True

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("user")
        if request.user.is_superuser:
            return qs
        if request.user.groups.filter(name="Магазины").exists():
            return qs.filter(user=request.user)
        return qs

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name="Магазины").exists():
            if obj is not None:
                return obj.user == request.user
            return True
        return super().has_change_permission(request, obj)

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name="Магазины").exists():
            return False
        return super().has_add_permission(request)

    def save_model(self, request, obj, form, change):
        if request.user.groups.filter(name="Магазины").exists():
            obj.user = request.user
        super().save_model(request, obj, form, change)

    def upload_yaml_view(self, request, shop_id):
        shop = get_object_or_404(Shop, id=shop_id)

        if request.method == "POST":
            form = UploadYAMLForm(request.POST, request.FILES)
            if form.is_valid():
                yaml_file = request.FILES["yaml_file"]

                if not yaml_file.name.lower().endswith((".yaml", ".yml")):
                    messages.error(
                        request, "Можно загружать только YAML-файлы (.yaml, .yml)."
                    )
                    return render(
                        request,
                        "admin/upload_yaml.html",
                        {
                            "form": form,
                            "shop": shop,
                        },
                    )

                try:
                    content = yaml_file.read().decode("utf-8")
                    data = yaml.safe_load(content)
                    task = process_shop_data_async.delay(data, request.user.id)
                    messages.success(
                        request,
                        f"Файл успешно загружен. Задача запущена (ID: {task.id}). Проверьте логи Celery или состояние товаров."
                    )
                except Exception as e:
                    messages.error(request, f"Ошибка: {str(e)}")

                url = reverse("admin:backend_shop_change", args=[shop.id])
                return HttpResponseRedirect(url)
        else:
            form = UploadYAMLForm()

        return render(request, "admin/upload_yaml.html", {
            "form": form,
            "shop": shop,
            "title": "Загрузка YAML-файла",
        })


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
        qs = (
            super()
            .get_queryset(request)
            .prefetch_related("product_infos__parameters", "product_infos__shop")
        )
        if request.user.is_superuser:
            return qs
        if request.user.groups.filter(name="Магазины").exists():
            user_shops = request.user.shops.all()
            if not user_shops.exists():
                return qs.none()
            return qs.filter(product_infos__shop__in=user_shops).distinct()
        return qs

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name="Магазины").exists():
            if obj is None:
                return True
            user_shops = request.user.shops.all()
            return obj.product_infos.filter(shop__in=user_shops).exists()
        return super().has_change_permission(request, obj)

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name="Магазины").exists():
            return True
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        if request.user.groups.filter(name="Магазины").exists():
            if obj is not None:
                user_shops = request.user.shops.all()
                return obj.product_infos.filter(shop__in=user_shops).exists()
            return False
        return super().has_delete_permission(request, obj)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, ProductInfo):
                if not instance.pk and request.user.groups.filter(name="Магазины").exists():
                    user_shops = request.user.shops.all()
                    if user_shops.exists():
                        instance.shop = user_shops.first()
                instance.save()
            else:
                instance.save()
        formset.save_m2m()

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
        return super().get_queryset(request).select_related("product_info", "parameter")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("user", "dt", "status")
    search_fields = ("user__email", "status")
    list_filter = ("dt", "status")
    inlines = [OrderItemInline]
    readonly_fields = ["dt", "user"]

    def get_fields(self, request, obj=None):
        fields = ["dt", "user", "status"]
        if hasattr(obj, "delivery_address") or "delivery_address" in [
            f.name for f in obj._meta.get_fields()
        ]:
            fields.append("delivery_address")
        return fields

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = super().get_readonly_fields(request, obj)
        readonly_fields = list(readonly_fields)

        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name="Магазины").exists():
            if "delivery_address" not in readonly_fields:
                readonly_fields.append("delivery_address")

        return readonly_fields

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("user")
        if request.user.is_superuser:
            return qs
        if request.user.groups.filter(name="Магазины").exists():
            user_shops = request.user.shops.all()
            if not user_shops.exists():
                return qs.none()
            return qs.filter(items__product_info__shop__in=user_shops).distinct()
        return qs

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name="Магазины").exists():
            if obj is not None:
                user_shops = request.user.shops.all()
                return obj.items.filter(product_info__shop__in=user_shops).exists()
            return True
        return super().has_change_permission(request, obj)


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
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if request.user.groups.filter(name="Магазины").exists():
            return qs.filter(user=request.user)
        return qs

    def has_module_permission(self, request):
        return not request.user.groups.filter(name="Магазины").exists()

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name="Магазины").exists():
            return False
        return super().has_change_permission(request, obj)

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name="Магазины").exists():
            return not Contact.objects.filter(user=request.user).exists()
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name="Магазины").exists():
            if obj is not None:
                return obj.user == request.user
            return False
        return super().has_delete_permission(request, obj)

    user_email.short_description = "Email пользователя"
    formatted_phone.short_description = "Номер телефона"


@receiver(post_migrate)
def create_shop_group(sender, **kwargs):
    shop_group, created = Group.objects.get_or_create(name="Магазины")

    # Определяем модели и права
    models_and_perms = [
        (Shop, ["view", "change"]),
        (Product, ["view","add", "change"]),
        (ProductInfo, ["view", "add", "change", "delete"]),
        (ProductParameter, ["view", "add", "change", "delete"]),
        (Order, ["view", "change"]),
        (Contact, ["view", "add", "change"]),
    ]

    for model, perms in models_and_perms:
        try:
            content_type = ContentType.objects.get_for_model(model)
        except Exception:
            continue

        for perm in perms:
            codename = f"{perm}_{model._meta.model_name}"
            try:
                permission = Permission.objects.get(codename=codename, content_type=content_type)
                shop_group.permissions.add(permission)
            except Permission.DoesNotExist:
                pass