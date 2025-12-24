from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from backend.models import (
    Category,
    Contact,
    Order,
    OrderHistory,
    OrderItem,
    Product,
    ProductInfo,
    ProductParameter,
    Shop,
)
from backend.utils.normalizers import (
    is_valid_email,
    normalize_email,
    normalize_phone_number,
    validate_phone_number,
)

User = get_user_model()

class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = [
            "id", "zipcode", "city", "street",
            "building", "appartment"
        ]
        read_only_fields = ["id",]

    def validate_zipcode(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("Индекс должен содержать только цифры.")
        if len(value) != 6:
            raise serializers.ValidationError("Индекс должен содержать 6 цифр.")
        return value

    def validate_city(self, value):
        if len(value) < 2:
            raise serializers.ValidationError("Название города должно быть не менее 2 символов.")
        return value.strip()

    def validate_street(self, value):
        if len(value) < 2:
            raise serializers.ValidationError("Улица должна быть не менее 2 символов.")
        return value.strip()

    def validate_building(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Поле 'building' не может быть пустым.")
        return value

    def validate_appartment(self, value):
        if value is not None:
            value = value.strip()
            if value and len(value) > 10:
                raise serializers.ValidationError("Номер квартиры не должен превышать 10 символов.")
        return value


class UserSerializer(serializers.ModelSerializer):
    contacts = ContactSerializer(many=True, read_only=True)
    password = serializers.CharField(write_only=True)
    type = serializers.ChoiceField(
        choices=User.USER_TYPE_CHOICES,
        help_text="Тип пользователя: `shop` — магазин, `buyer` — покупатель.",
        error_messages={
            "invalid_choice": "Поле 'type' должно быть одним из: 'shop', 'buyer'."
        },
    )
    phone_number = serializers.CharField(
        validators=[validate_phone_number],
        required=False,
        allow_null=True,
        help_text="Формат: +7 (XXX) XX-XX-XX",
    )

    type_display = serializers.SerializerMethodField(
        read_only=True, help_text="Название типа пользователя"
    )

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "password",
            "username",
            "first_name",
            "last_name",
            "phone_number",
            "company",
            "position",
            "contacts",
            "type",
            "type_display",
        )
        read_only_fields = ["id"]
        extra_kwargs = {
            "password": {"write_only": True},
            "company": {"required": False},
            "position": {"required": False},
        }

    def get_type_display(self, obj):
        return "Магазин" if obj.type == "shop" else "Покупатель"

    def validate(self, attrs):
        # Если пользователь — магазин, проверяем обязательность company и position
        if attrs.get("type") == "shop":
            if not attrs.get("company"):
                raise serializers.ValidationError({
                    "company": "Это поле обязательно для пользователей с типом 'shop'."
                })
            if not attrs.get("position"):
                raise serializers.ValidationError({
                    "position": "Это поле обязательно для пользователей с типом 'shop'."
                })
        return attrs

    def validate_email(self, value):
        normalized = normalize_email(value)
        if not is_valid_email(normalized):
            raise serializers.ValidationError("Введите корректный email-адрес.")
        # Проверка уникальности
        if User.objects.filter(email=normalized).exists():
            raise serializers.ValidationError("Пользователь с таким email уже существует.")
        return normalized

    def validate_phone_number(self, value):
        normalized = normalize_phone_number(value)
        if not normalized:
            raise serializers.ValidationError(
                "Неверный формат номера телефона. Ожидается 10 или 11 цифр (с 8 или +7)."
            )
        return normalized

    @extend_schema_field(serializers.CharField)
    def get_type(self, obj):
        """
        Возвращает понятное название типа пользователя.
        """
        return "Магазин" if obj.type == "shop" else "Покупатель"

    def create(self, validated_data):
        # Извлекаем обязательные поля
        email=validated_data.pop("email")
        password=validated_data.pop("password")
        username=validated_data.pop("username")

        # Остальные поля будут переданы как extra_fields
        extra_fields = {k: v for k, v in validated_data.items() if hasattr(User(), k)}

        # Создаём пользователя с помощью create_user
        user = User.objects.create_user(
            email=email, password=password, username=username, **extra_fields
        )
        return user

    def update(self, instance, validated_data):
        # Обновляем email (если он был передан)
        if "email" in validated_data:
            email = validated_data.pop("email")
            instance.email = email

        # Обновляем пароль (если он был передан)
        if "password" in validated_data:
            instance.set_password(validated_data.pop("password"))

        # Обновляем остальные поля
        for attr, value in validated_data.items():
            if hasattr(instance, attr):
                setattr(instance, attr, value)

        instance.save()
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        phone = data.get("phone_number")
        if phone:
            # Формат: +7 (XXX) XX-XX-XX
            formatted_phone = (f"+{phone[:1]} "
                                f"({phone[1:4]}) "f"({phone[1:4]}) "
                                f"{phone[4:7]}-"
                                f"{phone[7:9]}-"
                                f"{phone[9:]}")
            data["phone_number"] = formatted_phone
        return data


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        if attrs["old_password"] == attrs["new_password"]:
            raise serializers.ValidationError("Новый пароль должен отличаться от старого.")
        return attrs


class SendEmailConfirmationSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


class VerifyEmailConfirmationSerializer(serializers.Serializer):
    email = serializers.EmailField(
        help_text="Email пользователя, указанный при регистрации."
    )
    code = serializers.CharField(
        max_length = 12,
        min_length = 12,
        required = True,
    )

class EmailStatusSerializer(serializers.Serializer):
    email = serializers.EmailField()
    sent = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    is_verified = serializers.BooleanField()


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name")
        read_only_fields = fields


class ShopListSerializer(serializers.ModelSerializer):
    owner = serializers.SerializerMethodField()
    categories_count = serializers.SerializerMethodField()
    state = serializers.SerializerMethodField()

    class Meta:
        model = Shop
        fields = (
            "id",
            "name",
            "slug",
            "url",
            "state",
            "owner",
            "categories_count",
        )

    @extend_schema_field(serializers.CharField)
    def get_owner(self, obj):
        return (
            f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.username
        )

    @extend_schema_field(serializers.BooleanField)
    def get_state(self, obj):
        return "Принимает заказы" if obj.state else "Не принимает заказы"

    @extend_schema_field(serializers.IntegerField)
    def get_categories_count(self, obj):
        return obj.categories.count()


class ShopDetailSerializer(serializers.ModelSerializer):
    """
    Сериализатор для детальной информации — включает список категорий.
    """
    owner = serializers.SerializerMethodField()
    state = serializers.SerializerMethodField()
    categories = CategorySerializer(many=True, read_only=True, source="categories.all")

    class Meta:
        model = Shop
        fields = (
            "id",
            "name",
            "url",
            "state",
            "owner",
            "categories",
        )

    @extend_schema_field(serializers.CharField)
    def get_owner(self, obj):
        return (
            f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.username
        )

    @extend_schema_field(serializers.BooleanField)
    def get_state(self, obj):
        return "Принимает заказы" if obj.state else "Не принимает заказы"


class ProductInfoSerializer(serializers.ModelSerializer):
    unit_of_measure_display = serializers.CharField(
        source="get_unit_of_measure_display",
        read_only=True
    )
    product_name = serializers.CharField(
        source="product.name",
        read_only=True
    )
    category_name = serializers.CharField(
        source="product.category.name",
        read_only=True
    )

    class Meta:
        model = ProductInfo
        fields = (
            "id",
            "product_name",
            "category_name",
            "model",
            "external_id",
            "price",
            "price_rrc",
            "quantity",
            "unit_of_measure",
            "unit_of_measure_display",
        )

        extra_kwargs = {
            "price": {"coerce_to_string": True},
            "price_rrc": {"coerce_to_string": True},
            "quantity": {"coerce_to_string": True},
            "unit_of_measure": {"read_only": True},
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not data.get("product_name"):
            data["product_name"] = "Не указано"
        if not data.get("category_name"):
            data["category_name"] = "Без категории"
        return data


class ProductSerializer(serializers.ModelSerializer):
    category = serializers.StringRelatedField()

    class Meta:
        model = Product
        fields = ["name", "category"]


class ProductParameterSerializer(serializers.ModelSerializer):
    parameter = serializers.StringRelatedField()

    class Meta:
        model = ProductParameter
        fields = [
            "parameter", "value"
        ]


class OrderItemSerializer(serializers.ModelSerializer):
    product_info = ProductInfoSerializer(read_only = True)
    status_display = serializers.CharField(source = "get_status_display", read_only = True)

    class Meta:
        model = OrderItem
        fields = [
            "id", "product_info", "quantity", "order", "quantity",
            "shop_confirmed", "status", "status_display", "created_at"
        ]
        read_only_fields = ["id",]
        extra_kwargs = {"order": {"write_only": True}}


class OrderItemCreateSerializer(serializers.ModelSerializer):
    product_info = ProductInfoSerializer(read_only=True)


class OrderSerializer(serializers.ModelSerializer):
    order_items = OrderItemSerializer(many=True, read_only=True)
    total_price = serializers.SerializerMethodField()
    user = UserSerializer(read_only=True)
    delivery_address = ContactSerializer(read_only=True)

    class Meta:
        model = Order
        fields = (
            "id", "user", "order_items", "status", "dt", "total_price", "delivery_address",
        )
        read_only_fields = ["id", "dt"]

    @extend_schema_field(serializers.DecimalField(max_digits=10, decimal_places=2))
    def get_total_price(self, obj):
        return sum(item.quantity * item.product_info.price for item in obj.order_items.all())


class OrderHistorySerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    user_email = serializers.SerializerMethodField()

    class Meta:
        model = OrderHistory
        fields = ["id", "action", "action_display", "details", "user_email", "created_at"]

    def get_user_email(self, obj):
        return obj.user.email if obj.user else None


class BasketItemSerializer(serializers.ModelSerializer):
    product_info = ProductInfoSerializer(read_only=True)
    product_info_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductInfo.objects.filter(shop__state=True),
        source="product_info",
        write_only=True
    )

    class Meta:
        model = OrderItem
        fields = ("id", "product_info", "product_info_id", "quantity")


class BasketItemDeleteSerializer(serializers.Serializer):
    id = serializers.IntegerField()


class BasketItemAddSerializer(serializers.Serializer):
    """
    Сериализатор для добавления товара в корзину.
    Принимает ID ProductInfo и количество.
    """
    product_info_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductInfo.objects.filter(shop__state=True),
        source="product_info"
    )
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=1)

    def validate_quantity(self, value):
        if value.as_integer_ratio()[1] != 1:  # Проверка на целое число (для штук)
            if self.initial_data.get("product_info_id"):
                product_info = ProductInfo.objects.filter(id=self.initial_data["product_info_id"]).first()
                if product_info and product_info.unit_of_measure == "pcs":
                    raise serializers.ValidationError("Количество должно быть целым числом для штучного товара.")
        return value

    def validate(self, data):
        product_info = data["product_info"]
        quantity = data["quantity"]

        if quantity > product_info.quantity:
            raise serializers.ValidationError(
                f"Доступно только {product_info.quantity} шт. товара '{product_info.product.name}'"
            )

        return data


class ProductInfoSearchSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    shop = serializers.CharField(source="shop.name", read_only=True)

    class Meta:
        model = ProductInfo
        fields = (
            "id",
            "product_name",
            "model",
            "shop",
            "price",
            "price_rrc",
            "quantity",
            "unit_of_measure",
        )
        read_only_fields = fields
