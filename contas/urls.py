# contas/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PerfilUsuarioView, UserRegistrationView, PasswordResetRequestView, PasswordResetConfirmView, UserAdminViewSet
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

# from .views import PerfilUsuarioView

# Roteador para os endpoints de administração de utilizadores
admin_router = DefaultRouter()
admin_router.register(r'users', UserAdminViewSet, basename='admin-user')

urlpatterns = [
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', PerfilUsuarioView.as_view(), name='perfil_usuario'),
    path('registrar/', UserRegistrationView.as_view(), name='user-register'),
    path('admin/', include(admin_router.urls)),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
]
