# contas/permissions.py

from rest_framework.permissions import BasePermission
from .models import Usuario

class IsAdminUser(BasePermission):
    """
    Permissão que permite o acesso apenas a utilizadores com o papel de Admin.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.papel == Usuario.Papel.ADMIN

class IsFotografoOrAdmin(BasePermission):
    """
    Permissão que permite o acesso a Fotógrafos OU Administradores.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.papel in [
            Usuario.Papel.FOTOGRAFO,
            Usuario.Papel.ADMIN
        ]

class IsCliente(BasePermission):
    """
    Permissão que permite o acesso apenas a utilizadores com o papel de Cliente.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.papel == Usuario.Papel.CLIENTE