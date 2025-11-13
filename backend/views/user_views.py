from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model, update_session_auth_hash
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from backend.loggers.backend_logger import logger
from backend.models import Contact, EmailChangeRequest, EmailConfirmation
from backend.serializers import (
    ChangePasswordSerializer,
    ContactSerializer,
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
    """
    Регистрация нового пользователя.
    Возвращает JWT-токены после успешного создания.
    """
    permission_classes = [AllowAny]
    queryset = User.objects.all()
    serializer_class = UserSerializer

    @extend_schema(summary="Регистрация нового пользователя и получение JWT-токенов")
    def create(self, request, *args, **kwargs):
        """
        Создаёт нового пользователя и возвращает JWT-токены.
        """
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
        """
        Проверяет email и пароль, возвращает JWT-токены при успехе.
        """
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

        if not user.is_active:
            return Response(
                {"error": "Аккаунт не активирован. Проверьте email."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not user.check_password(password):
            return Response(
                {"error": "Неверный пароль."}, status=status.HTTP_401_UNAUTHORIZED
            )

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
    """
    Выход пользователя: добавляет refresh-токен в чёрный список.
    Требует аутентификации.
    """
    permission_classes = [IsAuthenticated]
    queryset = User.objects.all()
    serializer_class = UserSerializer

    @extend_schema(summary="Выход пользователя из системы")
    def create(self, request, *args, **kwargs):
        """
        Добавляет refresh-токен в чёрный список.
        """
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
        """
        Проверяет старый пароль и устанавливает новый.
        """
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
    retrieve=extend_schema(
        parameters=[OpenApiParameter("id", int, OpenApiParameter.PATH)]
    ),
    list=extend_schema(
        summary="Получить список адресов",
        description="Возвращает все адреса доставки, привязанные к пользователю.",
        tags=["USER"],
        responses={200: ContactSerializer(many=True)},
        operation_id="user_contact_list",
    ),
    create=extend_schema(
        summary="Добавить новый адрес",
        description="Создаёт новый адрес доставки.",
        tags=["USER"],
        request=ContactSerializer,
        responses={201: ContactSerializer, 400: dict},
        operation_id="user_contact_create",
    ),
    update=extend_schema(
        summary="Полное обновление адреса",
        description="Полностью обновляет указанный адрес.",
        tags=["USER"],
        request=ContactSerializer,
        responses={200: ContactSerializer, 400: dict, 404: dict},
        operation_id="user_contact_update",
    ),
    partial_update=extend_schema(
        summary="Частичное обновление адреса",
        description="Обновляет только указанные поля адреса.",
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
    lookup_field = "pk"

    def get_queryset(self):
        return Contact.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
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
        Возвращает профиль пользователя и все его адреса доставки.
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
        Создаёт новый адрес доставки для пользователя.
        """
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """
        Полностью обновляет указанный адрес.
        """
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """
        Частично обновляет указанные поля адреса.
        """
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        Удаляет указанный адрес доставки.
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
- Поле `type` отображается как текст: `Магазин` или `Покупатель`.
    - `Магазин` — пользователь представляет магазин.
    - `Покупатель` — обычный покупатель.
        """.strip(),
        tags=["USER"],
        responses={200: UserSerializer},
        operation_id="user_profile_retrieve",
    ),
    partial_update=extend_schema(
        summary="Частично обновить профиль",
        description="""
Обновляет указанные поля профиля.
- **Телефонный номер** должен начинаться с `7` или `8` (формат России).
- Поле `type` может быть изменено только при наличии прав администратора (не доступно для обычного пользователя).
    Допустимые значения: `Магазин`, `Покупатель`.
        """.strip(),
        tags=["USER"],
        request=UserSerializer,
        responses={200: UserSerializer, 400: dict, 403: dict},
        operation_id="user_profile_partial_update",
    ),
    update=extend_schema(
        exclude=True
    ),
)
class UserProfileViewSet(viewsets.GenericViewSet, mixins.RetrieveModelMixin, mixins.UpdateModelMixin):
    """
    Получение и частичное обновление профиля пользователя.
    Требует аутентификации.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

    def partial_update(self, request, *args, **kwargs):
        """
        Обновляет указанные поля профиля.
        Поле `type` может изменить только администратор.
        """
        instance = self.get_object()
        data = request.data.copy()

        # Удаляем поле 'type' из данных, если пользователь не является администратором
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
            logger.warning(
                f"Попытка подтвердить email для несуществующего пользователя: {normalized_email}"
            )
            return Response(
                {"error": "Пользователь с таким email не найден."},
                status=status.HTTP_404_NOT_FOUND
            )

        code = generate_code(12)
        EmailConfirmation.objects.filter(user=user).delete()
        EmailConfirmation.objects.create(user=user, code=code)

        send_email_confirmation.delay(
            email=normalized_email,
            subject="Код подтверждения",
            message=f"Ваш код подтверждения: {code}\nОн действителен 10 минут.",
            from_email=None
        )

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
        operation_id="user_verify_email_confirmation",
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


class UserChangeEmailRequestView(APIView):
    """
    Запрос на изменение email.
    Пользователь должен быть аутентифицирован.
    На новый email отправляется код подтверждения.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Запрос на изменение email",
        description="""
Позволяет авторизованному пользователю изменить email.
- На новый email отправляется 12-значный код подтверждения.
- Старый email остаётся активным до подтверждения нового.
- Письмо отправляется от администратора сайта.
        """.strip(),
        tags=["USER"],
        request=inline_serializer(
            name="ChangeEmailRequest",
            fields={
                "new_email": serializers.EmailField(help_text="Новый email пользователя")
            }
        ),
        responses={
            200: {"type": "object", "properties": {"success": {"type": "string"}}},
            400: {"type": "object", "properties": {"error": {"type": "string"}}},
        },
        operation_id="user_change_email_request",
    )
    def post(self, request):
        new_email = request.data.get("new_email")
        if not new_email:
            return Response(
                {"error": "Требуется поле 'new_email'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        normalized_new_email = new_email.strip().lower()

        try:
            validate_email(normalized_new_email)
        except ValidationError:
            return Response(
                {"error": "Некорректный формат email."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if normalized_new_email == request.user.email:
            return Response(
                {"error": "Новый email совпадает с текущим."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if User.objects.filter(email=normalized_new_email).exists():
            return Response(
                {"error": "Пользователь с таким email уже существует."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Генерируем код
        code = generate_code(12)

        # Сохраняем запрос на изменение
        EmailChangeRequest.objects.update_or_create(
            user=request.user,
            defaults={
                "new_email": normalized_new_email,
                "code": code,
                "created_at": timezone.now(),
                "is_verified": False
            }
        )

        # Отправка письма на новый email
        send_email_confirmation.delay(
            email=normalized_new_email,
            subject="Подтверждение изменения email",
            message=f"Ваш код для подтверждения смены email: {code}\n\nЭто письмо отправлено от администратора сайта.",
            from_email=None
        )

        logger.info(
            f"Код смены email отправлен на {normalized_new_email} для пользователя {request.user.id}"
        )

        return Response(
            {"success": f"Код отправлен на {normalized_new_email}"},
            status=status.HTTP_200_OK,
        )


class UserVerifyEmailChangeView(APIView):
    """
    Подтверждение изменения email по коду.
    Пользователь должен быть аутентифицирован.
    """

    permission_classes = [IsAuthenticated]

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
        code = request.data.get("code")
        if not code:
            return Response(
                {"error": "Требуется поле 'code'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            change_request = EmailChangeRequest.objects.get(user=request.user)
        except EmailChangeRequest.DoesNotExist:
            return Response(
                {"error": "Запрос на смену email не найден. Сначала отправьте код."},
                status=status.HTTP_404_NOT_FOUND
            )

        if timezone.now() - change_request.created_at > timedelta(minutes=10):
            change_request.delete()
            return Response(
                {"error": "Срок действия кода истёк. Запросите новый."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if change_request.code != code:
            return Response(
                {"error": "Неверный код."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Обновляем email пользователя
        old_email = request.user.email
        request.user.email = change_request.new_email
        request.user.save()

        # Помечаем как подтверждённое
        change_request.is_verified = True
        change_request.save()

        logger.info(f"Email пользователя {request.user.id} изменён с {old_email} на {change_request.new_email}")

        return Response(
            {"success": f"Email успешно изменён на {change_request.new_email}"},
            status=status.HTTP_200_OK
        )