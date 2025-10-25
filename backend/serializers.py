from __future__ import annotations

from rest_framework import serializers

from backend.models import (
    Category,
    Contact,
    Order,
    OrderItem,
    Product,
    ProductInfo,
    ProductParameter,
    Shop,
    User,
)


def validate_phone_number(value: str) -> str:
    digits = "".join(filter(str.isdigit, value))

    if len(digits) != 11:
        raise serializers.ValidationError("Неверный формат номера. Пример: +7 (999) 123-45-67")

    if not digits.startswith("7"):
        raise serializers.ValidationError("Номер должен быть в формате РФ (начинаться с 7)")

    return digits


class ContactPhoneSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(
        source="phone_number",
        validators=[validate_phone_number],
        required=False,
        allow_null=True,
        help_text="Формат: +7 (XXX) XX-XX-XX"
    )

    class Meta:
        model = Contact
        fields = [
            "user", "city", "street", "building", "appartment", "phone_number"
        ]

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

class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = [
            "id","user", "city", "street", "building", "appartment", "phone_number"
        ]
        read_only_fields = ["id",]
        extra_kwargs = {
            "user": {"write_only": True}
        }


class UserSerializer(serializers.ModelSerializer):
    contacts = ContactSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "company", "position", "contacts",
        ]
        read_only_fields = ["id",]

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = [
            "id", "name"
        ]
        read_only_fields = ["id",]


class ShopSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shop
        fields = [
            "id", "name", "state"
        ]
        read_only_fields = ["id",]

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


class ProductInfoSerializer(serializers.ModelSerializer):
    product = serializers.StringRelatedField()
    product_parameters = ProductParameterSerializer(many=True, read_only=True)

    class Meta:
        model = ProductInfo
        fields = [
            "id", "model", "product", "quantity", "shop", "price", "price_rrc", "product_parameters",
        ]
        read_only_fields = ["id",]


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = [
            "id", "product_info", "quantity", "order"
        ]
        read_only_fields = ["id",]
        extra_kwargs = {"order": {"write_only": True}}


class OrderItemCreateSerializer(serializers.ModelSerializer):
    product_info = ProductInfoSerializer(read_only=True)


class OrderSerializer(serializers.ModelSerializer):
    order_items = OrderItemSerializer(many=True, read_only=True)

    total_price = serializers.IntegerField()
    contact = ContactSerializer(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "order_items", "status", "dt", "total_price", "contact"
        ]
        read_only_fields = ["id",]
