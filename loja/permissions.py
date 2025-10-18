# loja/permissions.py
from rest_framework.permissions import BasePermission
from contas.models import Usuario

class IsFotografo(BasePermission):
    """
    Permissão que permite o acesso apenas a utilizadores com o papel de Fotógrafo.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.papel == Usuario.Papel.FOTOGRAFO

class IsCliente(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.papel == Usuario.Papel.CLIENTE
    