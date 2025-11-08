from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model, update_session_auth_hash
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from backend.loggers.backend_logger import logger
from backend.models import Contact, EmailConfirmation
from backend.serializers import (
    ChangePasswordSerializer,
    ContactSerializer,
    EmailStatusSerializer,
    SendEmailConfirmationSerializer,
    UserSerializer,
    VerifyEmailConfirmationSerializer,
)
from backend.tasks import send_email_confirmation
from backend.utils.generators import generate_code
from backend.utils.normalizers import normalize_email
from backend.utils.throttling import (
    LoginThrottle,
)

User = get_user_model()

@extend_schema_view(
    create=extend_schema(
        summary="Регистрация нового пользователя",
        description="""
Регистрирует нового пользователя. 
- **Телефонный номер** должен начинаться с `7` или `8` (формат России).
- Поле `type` может принимать одно из двух значений: `shop` или `buyer`.
    - `shop` — пользователь представляет магазин.
    - `buyer` — обычный покупатель.
        """.strip(),
        tags=["USER"],
        request=UserSerializer,
        responses={
            201: {
                "type": "object",
                "properties": {
                    "refresh": {"type": "string", "example": "eyJ..."},
                    "access": {"type": "string", "example": "eyJ..."}
                }
            },
            400: {"type": "object", "properties": {"error": {"type": "string"}}},
            500: {"type": "object", "properties": {"error": {"type": "string"}}},
        },
        operation_id="user_register",
    )
)
class UserRegisterViewSet(viewsets.GenericViewSet, mixins.CreateModelMixin):
    permission_classes = [AllowAny]
    queryset = User.objects.all()
    serializer_class = UserSerializer

    @extend_schema(summary="Регистрация нового пользователя и получение JWT-токенов")
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = serializer.save()
        except Exception:
            return Response(
                {"error": "Ошибка при создании пользователя"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        refresh = RefreshToken.for_user(user)
        refresh.payload.update({
            "user_id": user.id,
            "email": user.email,
        })

        return Response({
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }, status=status.HTTP_201_CREATED)


@extend_schema_view(
    post=extend_schema(
        summary="Авторизация пользователя",
        description="Возвращает JWT-токены (`access` и `refresh`) при корректных email и пароле.",
        tags=["USER"],
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "format": "email", "example": "user@example.com"},
                    "password": {"type": "string", "format": "password", "example": "strongpassword123"}
                },
                "required": ["email", "password"]
            }
        },
        responses={
            200: {
                "type": "object",
                "properties": {
                    "refresh": {"type": "string", "example": "eyJ..."},
                    "access": {"type": "string", "example": "eyJ..."}
                }
            },
            400: {"type": "object", "properties": {"error": {"type": "string"}}},
            401: {"type": "object", "properties": {"error": {"type": "string"}}},
            403: {"type": "object", "properties": {"error": {"type": "string"}}},
            404: {"type": "object", "properties": {"error": {"type": "string"}}},
        },
        operation_id="user_login",
    )
)
class UserLoginView(APIView):
    """
    Авторизация пользователя по email и паролю.
    Возвращает JWT-токены.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        if not email or not password:
            return Response(
                {"error": "Требуются email и пароль."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        normalized_email = normalize_email(email)

        try:
            user = User.objects.get(email=normalized_email)
        except User.DoesNotExist:
            return Response(
                {"error": "Пользователь не найден."}, status=status.HTTP_404_NOT_FOUND
            )

        # Проверяем, активен ли аккаунт
        if not user.is_active:
            return Response(
                {"error": "Аккаунт не активирован. Проверьте email."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Проверяем пароль
        if not user.check_password(password):
            return Response(
                {"error": "Неверный пароль."}, status=status.HTTP_401_UNAUTHORIZED
            )

        # Генерируем JWT-токены
        refresh = RefreshToken.for_user(user)
        refresh.payload.update(
            {
                "user_id": user.id,
                "email": user.email,
            }
        )

        return Response({
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }, status=status.HTTP_200_OK)


@extend_schema_view(
    create=extend_schema(
        summary="Выход пользователя",
        description="Добавляет `refresh`-токен в чёрный список, делая его недействительным.",
        tags=["USER"],
        request=inline_serializer(
            name="LogoutRequest",
            fields={"refresh_token": serializers.CharField()}
        ),
        responses={
            200: {"type": "object", "properties": {"success": {"type": "string"}}},
            400: {"type": "object", "properties": {"error": {"type": "string"}}},
        },
        operation_id="user_logout",
    )
)
@throttle_classes([LoginThrottle])
class UserLogoutViewSet(viewsets.GenericViewSet, mixins.CreateModelMixin):
    permission_classes = [IsAuthenticated]
    queryset = User.objects.all()
    serializer_class = UserSerializer

    @extend_schema(summary="Выход пользователя из системы")
    def create(self, request, *args, **kwargs):
        refresh_token = request.data.get("refresh_token")
        if not refresh_token:
            return Response(
                {"error": "Необходим Refresh token"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            # Логируем ошибку (опционально)
            return Response(
                {"error": "Неверный или истёкший Refresh token"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"success": "Выход успешен"}, status=status.HTTP_200_OK)


@extend_schema_view(
    change_password=extend_schema(
        summary="Смена пароля пользователя",
        description="Позволяет авторизованному пользователю изменить свой пароль.",
        tags=["USER"],
        request=ChangePasswordSerializer,
        responses={
            200: {"type": "object", "properties": {"success": {"type": "string"}}},
            400: {"type": "object", "properties": {"error": {"type": "string"}}},
        },
        operation_id="user_change_password",
    )
)
class UserChangePasswordViewSet(viewsets.GenericViewSet):
    """
    Эндпоинт для смены пароля.
    Пользователь должен быть авторизован.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    @action(detail=False, methods=["post"], url_path="change", url_name="change")
    def change_password(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        old_password = serializer.validated_data["old_password"]
        new_password = serializer.validated_data["new_password"]

        if not user.check_password(old_password):
            return Response(
                {"error": "Текущий пароль введён неверно."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.save()
        update_session_auth_hash(request, user)  # Сохраняет сессию

        return Response(
            {"success": "Пароль успешно изменён"},
            status=status.HTTP_200_OK
        )


@extend_schema_view(
    list=extend_schema(
        summary="Получить список адресов",
        description="Возвращает все адреса доставки, привязанные к пользователю.",
        tags=["USER"],
        responses={200: ContactSerializer(many=True)},
        operation_id="user_contact_list",
    ),
    create=extend_schema(
        summary="Добавить новый адрес",
        description="""
Создаёт новый адрес доставки.
- Поле `phone` (если передаётся) должно быть в формате России — начинаться с `7` или `8`.
        """.strip(),
        tags=["USER"],
        request=ContactSerializer,
        responses={201: ContactSerializer, 400: dict},
        operation_id="user_contact_create",
    ),
    update=extend_schema(
        summary="Полное обновление адреса",
        description="""
Полностью обновляет указанный адрес.
- Номер телефона должен начинаться с `7` или `8`.
        """.strip(),
        tags=["USER"],
        request=ContactSerializer,
        responses={200: ContactSerializer, 400: dict, 404: dict},
        operation_id="user_contact_update",
    ),
    partial_update=extend_schema(
        summary="Частичное обновление адреса",
        description="""
Обновляет только указанные поля адреса.
- Если обновляется `phone`, он должен начинаться с `7` или `8`.
        """.strip(),
        tags=["USER"],
        request=ContactSerializer,
        responses={200: ContactSerializer, 400: dict, 404: dict},
        operation_id="user_contact_partial_update",
    ),
    destroy=extend_schema(
        summary="Удалить адрес",
        description="Удаляет указанный адрес доставки.",
        tags=["USER"],
        responses={204: dict, 404: dict},
        operation_id="user_contact_destroy",
    ),
    me=extend_schema(
        summary="Получить профиль + адреса",
        description="Возвращает данные пользователя и все его адреса доставки.",
        tags=["USER"],
        responses=inline_serializer(
            name="UserContactMeResponse",
            fields={
                "user_id": serializers.IntegerField(),
                "username": serializers.CharField(),
                "email": serializers.EmailField(),
                "first_name": serializers.CharField(required=False),
                "last_name": serializers.CharField(required=False),
                "phone_number": serializers.CharField(required=False),
                "company": serializers.CharField(required=False),
                "position": serializers.CharField(required=False),
                "type": serializers.CharField(),
                "addresses": ContactSerializer(many=True),
            },
        ),
        operation_id="user_contact_me",
    ),
)
class UserContactViewSet(viewsets.GenericViewSet,
                        mixins.ListModelMixin,
                        mixins.CreateModelMixin,
                        mixins.UpdateModelMixin,
                        mixins.DestroyModelMixin):
    """
    Управление адресами пользователя:
    - GET /user/contact/ — список адресов
    - POST /user/contact/ — создать адрес
    - PUT/PATCH /user/contact/<id>/ — обновить
    - DELETE /user/contact/<id>/ — удалить
    - GET /user/contact/me/ — профиль + все адреса
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ContactSerializer

    def get_queryset(self):
        # Пользователь видит только свои контакты
        return Contact.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        # Привязываем контакт к текущему пользователю
        serializer.save(user=self.request.user)

    @extend_schema(
        summary="Получить полную контактную информацию",
        tags=["USER"],
        responses=inline_serializer(
            name="UserContactMeResponse",
            fields={
                "user_id": serializers.IntegerField(),
                "username": serializers.CharField(),
                "email": serializers.EmailField(),
                "first_name": serializers.CharField(required=False),
                "last_name": serializers.CharField(required=False),
                "phone_number": serializers.CharField(required=False),
                "company": serializers.CharField(required=False),
                "position": serializers.CharField(required=False),
                "type": serializers.CharField(),
                "addresses": ContactSerializer(many=True),
            },
        ),
    )
    @action(detail=False, methods=["get"], url_path="me", url_name="me")
    def me(self, request, *args, **kwargs):
        """
        Получение контактной информации пользователя: профиль + все адреса.
        """
        user = request.user

        contacts = self.get_queryset()
        contacts_data = ContactSerializer(contacts, many=True).data

        user_contact_info = {
            "user_id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone_number": user.phone_number,
            "company": user.company,
            "position": user.position,
            "type": user.get_type_display(),
            "addresses": contacts_data,
        }

        return Response(user_contact_info, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        """
        Создание нового адреса для пользователя.
        """
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """
        Полное обновление контакта.
        """
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """
        Частичное обновление контакта.
        """
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        Удаление контакта.
        """
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(
            {"success": "Адрес успешно удалён"},
            status=status.HTTP_204_NO_CONTENT
        )


@extend_schema_view(
    retrieve=extend_schema(
        summary="Получить профиль",
        description="""
Возвращает основную информацию о текущем пользователе.
- **Телефонный номер** должен начинаться с `7` или `8` (формат России).
- Поле `type` отображается как текст: `shop` или `buyer`.
    - `shop` — пользователь представляет магазин.
    - `buyer` — обычный покупатель.
        """.strip(),
        tags=["USER"],
        responses=UserSerializer,
        operation_id="user_profile_retrieve",
    ),
    partial_update=extend_schema(
        summary="Частично обновить профиль",
        description="""
Обновляет указанные поля профиля.
- **Телефонный номер** должен начинаться с `7` или `8` (формат России).
- Поле `type` может быть изменено только при наличии прав (не досупно для обычного пользователя).
    Допустимые значения: `shop`, `buyer`.
        """.strip(),
        tags=["USER"],
        request=UserSerializer,
        responses={200: UserSerializer, 400: dict},
        operation_id="user_profile_partial_update",
    ),
    update=extend_schema(exclude=True),
)
class UserProfileViewSet(viewsets.GenericViewSet, mixins.RetrieveModelMixin, mixins.UpdateModelMixin):
    """
    Управление профилем пользователя:
    - GET /user/profile/ — данные профиля
    - PATCH /user/profile/ — частично обновить профиль
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        # Возвращаем текущего пользователя
        return self.request.user

    def profile(self, request, *args, **kwargs):
        if request.method == "GET":
            return self.retrieve(request, *args, **kwargs)
        elif request.method == "PATCH":
            return self.partial_update(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        data = request.data.copy()

        # Защита поля `type`: только администратор может его изменить
        if "type" in data and not request.user.is_staff and not request.user.is_superuser:
            return Response(
                {"error": "Изменение поля 'type' доступно только администраторам."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(instance, data=data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class UserSendEmailConfirmationView(APIView):
    """
    Отправка кода подтверждения на email.
    Доступно без авторизации.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Отправить код подтверждения email",
        description="""
Отправляет 12-значный код на email для подтверждения аккаунта.
- Доступно без авторизации.
- Письмо отправляется от имени администратора сайта.
- Повторная отправка ограничена (3 раза в час).
- Работает только для зарегистрированных пользователей.
        """.strip(),
        tags=["USER"],
        request=SendEmailConfirmationSerializer,
        responses={
            200: {"type": "object", "properties": {"success": {"type": "string"}}},
            400: {"type": "object", "properties": {"error": {"type": "string"}}},
            404: {"type": "object", "properties": {"error": {"type": "string"}}}
        },
        operation_id="user_send_confirmation_code",
    )
    def post(self, request):
        serializer = SendEmailConfirmationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]
        normalized_email = email.strip().lower()

        try:
            validate_email(normalized_email)
        except ValidationError:
            return Response(
                {"error": "Некорректный формат email."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(email=normalized_email)
        except User.DoesNotExist:
            logger.warning(f"Попытка подтвердить email для несуществующего пользователя: {normalized_email}")
            return Response(
                {"error": "Пользователь с таким email не найден."},
                status=status.HTTP_404_NOT_FOUND
            )

        code = generate_code(12)
        EmailConfirmation.objects.filter(user=user).delete()
        EmailConfirmation.objects.create(user=user, code=code)

        send_email_confirmation.delay(email=normalized_email, code=code)

        logger.info(f"Код подтверждения отправлен на email: {normalized_email}")

        return Response(
            {"success": f"Код отправлен на {normalized_email}"},
            status=status.HTTP_200_OK,
        )


class UserVerifyEmailConfirmationView(APIView):
    """
    Подтверждение email по коду.
    Доступно без авторизации — для активации нового аккаунта.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Подтвердить email по коду",
        description="""
    Позволяет пользователю подтвердить email с помощью 12-значного кода.
    - **Не требует авторизации** — используется при активации аккаунта.
    - Код действует 10 минут.
    - После подтверждения аккаунт активируется.
            """.strip(),
        tags=["USER"],
        request=VerifyEmailConfirmationSerializer,
        responses={
            200: {"type": "object", "properties": {"success": {"type": "string"}}},
            400: {"type": "object", "properties": {"error": {"type": "string"}}},
            404: {"type": "object", "properties": {"error": {"type": "string"}}},
        },
        operation_id="user_verify_confirmation_code",
    )
    def post(self, request):
        serializer = VerifyEmailConfirmationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]
        code = serializer.validated_data["code"]
        normalized_email = email.strip().lower()

        try:
            validate_email(normalized_email)
        except ValidationError:
            return Response(
                {"error": "Некорректный формат email."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=normalized_email)
        except User.DoesNotExist:
            return Response(
                {"error": "Пользователь не найден."}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            confirmation = EmailConfirmation.objects.get(user=user)
        except EmailConfirmation.DoesNotExist:
            return Response(
                {"error": "Код не найден. Отправьте код снова."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if timezone.now() - confirmation.created_at > timedelta(minutes=10):
            confirmation.delete()
            return Response(
                {"error": "Код истёк. Запросите новый."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if confirmation.code != code:
            return Response(
                {"error": "Неверный код."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Активируем пользователя
        confirmation.is_verified = True
        confirmation.save()

        user.is_email_verified = True
        user.is_active = True
        user.save()

        return Response(
            {"success": "Email успешно подтверждён! Аккаунт активирован."},
            status=status.HTTP_200_OK
        )