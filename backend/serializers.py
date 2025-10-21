from __future__ import annotations

from rest_framework import serializers

from backend.models import Contact


def validate_phone_number(value: str) -> str:
    digits = "".join(filter(str.isdigit, value))

    if len(digits) != 11:
        raise serializers.ValidationError("Неверный формат номера. Пример: +7 (999) 123-45-67")

    if not digits.startswith("7"):
        raise serializers.ValidationError("Номер должен быть в формате РФ (начинаться с 7)")

    return digits


class ContactSerializer(serializers.ModelSerializer):
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
