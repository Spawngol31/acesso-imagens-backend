from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario

@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    model = Usuario
    # Campos que aparecerão na lista de usuários
    list_display = ('email', 'username', 'nome_completo', 'papel', 'is_staff')
    # Campos que podem ser usados para filtrar
    list_filter = ('papel', 'is_staff', 'is_superuser')
    # Campos para busca
    search_fields = ('email', 'nome_completo', 'username')
    # Ordenação padrão
    ordering = ('email',)

    # Sobrescreve os fieldsets para adequar ao nosso modelo
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Informações Pessoais', {'fields': ('username', 'nome_completo', 'papel')}),
        ('Permissões', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Datas Importantes', {'fields': ('last_login', 'date_joined')}),
    )