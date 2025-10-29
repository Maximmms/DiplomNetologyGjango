from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from backend.serializers import UserSerializer

User = get_user_model()


@api_view(["GET"])
def hello_view(request):
    return Response({"message": "Hello, World!"})


class UserRegisterView(APIView):
    def post(self, request):
        serializer = UserSerializer(data=request.data)
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


class UserLoginView(APIView):
    def post(self, request):
        data = request.data
        email = data.get("email")
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


class UserLogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
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

class PriceUpdateView(APIView):
    def post(self, request, *args, **kwargs):
        pass
