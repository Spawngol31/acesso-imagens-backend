# contas/permissions.py
from rest_framework.permissions import BasePermission
from .models import Usuario

class IsAdminUser(BasePermission):
    """
    Permissão que permite o acesso apenas a utilizadores com o papel de Administrador.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.papel == Usuario.Papel.ADMIN