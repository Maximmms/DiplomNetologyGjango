from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model, update_session_auth_hash
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
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

User = get_user_model()

@extend_schema_view(
    create=extend_schema(
        summary="Регистрация нового пользователя",
        description="Создаёт нового пользователя и возвращает JWT-токены (access и refresh).",
        tags=["USER"],
        responses={201: dict, 400: dict, 500: dict},
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
    create=extend_schema(
        summary="Авторизация пользователя",
        description="Возвращает JWT-токены (access и refresh) при корректных email и пароле.",
        tags=["USER"],
        responses={200: dict, 400: dict, 401: dict, 403: dict, 404: dict},
        operation_id="user_login",
    )
)
class UserLoginViewSet(viewsets.GenericViewSet, mixins.CreateModelMixin):
    permission_classes = [AllowAny]
    queryset = User.objects.all()
    serializer_class = UserSerializer

    @extend_schema(summary="Авторизация пользователя и получение JWT-токенов")
    def create(self, request, *args, **kwargs):
        data = request.data
        email = normalize_email(data.get("email"))
        password = data.get("password")

        if not email or not password:
            return Response(
                {"error": f"Необходимо указать email и пароль {request}:{request.data}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"error": "Пользователь не найден"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not user.check_password(password):
            return Response(
                {"error": "Неверный пароль"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {"error": "Аккаунт не активирован"},
                status=status.HTTP_403_FORBIDDEN,
            )

        refresh = RefreshToken.for_user(user)
        refresh.payload.update({"user_id": user.id, "email": user.email})

        return Response(
            {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            },
            status=status.HTTP_200_OK,
        )


@extend_schema_view(
    create=extend_schema(
        summary="Выход пользователя (черный список refresh-токена)",
        description="Добавляет refresh-токен в чёрный список, чтобы он больше не мог быть использован.",
        tags=["USER"],
        request=dict,
        responses={200: dict, 400: dict},
        operation_id="user_logout",
    )
)
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
            200: {
                "type": "object",
                "properties": {
                    "success": {"type": "string"}
                }
            },
            400: {"type": "object", "properties": {"error": {"type": "string"}}}
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
        summary="Получить список адресов пользователя",
        description="Возвращает все адреса, привязанные к текущему пользователю.",
        tags=["USER"],
        responses={200: ContactSerializer(many=True)},
        operation_id="user_contact_list",
    ),
    create=extend_schema(
        summary="Добавить новый адрес",
        description="Создаёт новый адрес доставки для пользователя.",
        tags=["USER"],
        responses={201: ContactSerializer, 400: dict},
        operation_id="user_contact_create",
    ),
    update=extend_schema(
        summary="Обновить адрес",
        description="Полное обновление адреса.",
        tags=["USER"],
        responses={200: ContactSerializer, 400: dict, 404: dict},
        operation_id="user_contact_update",
    ),
    partial_update=extend_schema(
        summary="Частично обновить адрес",
        description="Частичное обновление полей адреса.",
        tags=["USER"],
        responses={200: ContactSerializer, 400: dict, 404: dict},
        operation_id="user_contact_partial_update",
    ),
    destroy=extend_schema(
        summary="Удалить адрес",
        description="Удаляет указанный адрес.",
        tags=["USER"],
        responses={204: dict, 404: dict},
        operation_id="user_contact_destroy",
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
        summary="Получить профиль пользователя",
        description="Возвращает основную информацию о текущем пользователе.",
        tags=["USER"],
        responses=UserSerializer,
        operation_id="user_profile_retrieve",
    ),
    partial_update=extend_schema(
        summary="Частично обновить профиль пользователя",
        description="Обновляет указанные поля профиля пользователя (например, имя, телефон и т.п.).",
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
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    send_confirmation_code=extend_schema(
        summary="Отправить код подтверждения на email",
        description="Отправляет 12-значный код на email пользователя для подтверждения.",
        tags=["USER"],
        request=SendEmailConfirmationSerializer,
        responses={200: dict, 400: dict, 403: dict},
        operation_id="user_send_confirmation_code",
    ),
    verify_confirmation_code=extend_schema(
        summary="Подтвердить email по коду",
        description="Проверяет код подтверждения и устанавливает флаг is_verified.",
        tags=["USER"],
        request=VerifyEmailConfirmationSerializer,
        responses={200: dict, 400: dict, 404: dict},
        operation_id="user_verify_confirmation_code",
    ),
)
class UserEmailConfirmationViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = SendEmailConfirmationSerializer

    @action(detail=False, methods=["post"], url_path="email/send", url_name="comfirm-send")
    def send_confirmation_code(self, request):
        logger.info(f"Запрос на отправку кода подтверждения от пользователя {request.user.id}")
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]

        if request.user.email != normalize_email(email):
            return Response(
                {"error": "Email не совпадает с вашим аккаунтом."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Генерируем 12 значный код
        code = generate_code()

        # Удаляем старые коды
        EmailConfirmation.objects.filter(user=request.user).delete()

        # Создаем новый код
        EmailConfirmation.objects.create(user=request.user, code=code)

        #Отправка письма (Используем celery)
        send_email_confirmation.delay(email=email, code=code)

        return Response(
            {"success": f"Код отправлен на {email}"},
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=["post"], url_path="email/verify", url_name="comfirm-verify")
    def verify_confirmation_code(self, request):
        serializer = VerifyEmailConfirmationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        code = serializer.validated_data["code"]

        try:
            confirmation = EmailConfirmation.objects.get(user=request.user)
            logger.info(f"Код сгенерирован для пользователя {request.user.id}")
        except EmailConfirmation.DoesNotExist:
            return Response(
                {"error": "Код не найден. Сначала отправьте код."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Проверяе скрок действия кода (10 минут)
        if timezone.now() - confirmation.created_at > timedelta(minutes=10):
            confirmation.delete() # Удаляем код, если он просрочен
            return Response(
                {"error": "Код истёк. Запросите новый."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if confirmation.code != code:
            return Response(
                {"error": "Неверный код."}, status=status.HTTP_400_BAD_REQUEST
            )

        confirmation.is_verified = True
        confirmation.save()

        request.user.is_email_verified = True # Устанавливаем флаг подтверждения (is_email_verified)
        request.user.is_active = True # Активируем аккаунт
        request.user.save()

        return Response(
            {"success": "Email успешно подтверждён!"},
            status=status.HTTP_200_OK
        )


@extend_schema_view(
    status=extend_schema(
        summary="Получить статус подтверждения email",
        description="Возвращает статус: отправлен ли код и подтверждён ли email.",
        tags=["USER"],
        responses=EmailStatusSerializer,
        operation_id="user_email_status",
    )
)
class UserEmailStatusViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = EmailStatusSerializer

    @action(detail=False, methods=["get"], url_path="status", url_name="status")
    def status(self, request):
        user = request.user
        try:
            confirmation = EmailConfirmation.objects.get(user=user)
            data = {
                "email": user.email,
                "sent": True,
                "created_at": confirmation.created_at,
                "is_verified": confirmation.is_verified,
            }
        except EmailConfirmation.DoesNotExist:
            data = {
                "email": user.email,
                "sent": False,
                "created_at": None,
                "is_verified": getattr(user, "is_email_verified", False),
            }

        return Response(data, status=status.HTTP_200_OK)
