# contas/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario
from .forms import CustomUserCreationForm, CustomUserChangeForm
# 1. Importa os modelos de perfil
from perfis.models import PerfilCliente, PerfilFotografo

# 2. Cria as classes 'inline' para os perfis
class PerfilClienteInline(admin.StackedInline):
    model = PerfilCliente
    can_delete = False
    verbose_name_plural = 'Perfil de Cliente'
    fk_name = 'usuario'

class PerfilFotografoInline(admin.StackedInline):
    model = PerfilFotografo
    can_delete = False
    verbose_name_plural = 'Perfil de Fotógrafo'
    fk_name = 'usuario'

@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    model = Usuario
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm

    list_display = ('email', 'nome_completo', 'papel', 'is_staff')
    list_filter = ('papel', 'is_staff', 'is_superuser')
    search_fields = ('email', 'nome_completo')
    ordering = ('email',)

    # 3. Define quais 'inlines' mostrar
    # (Esta lógica será usada para mostrar o inline correto
    #  dependendo do papel do utilizador)
    inlines = [PerfilClienteInline, PerfilFotografoInline]

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Informações Pessoais', {'fields': ('nome_completo', 'papel')}),
        ('Permissões', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Datas Importantes', {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'nome_completo', 'papel', 'password', 'password2'),
        }),
    )

    # 4. Lógica para esconder os 'inlines' incorretos
    def get_inline_instances(self, request, obj=None):
        if not obj:
            return []
        
        inlines = self.inlines
        # Se o utilizador é um cliente, mostra apenas o perfil de cliente
        if obj.papel == Usuario.Papel.CLIENTE:
            inlines = [PerfilClienteInline]
        # Se for fotógrafo, mostra apenas o perfil de fotógrafo
        elif obj.papel == Usuario.Papel.FOTOGRAFO:
            inlines = [PerfilFotografoInline]
        # Se for Admin ou outro, não mostra nenhum
        else:
            inlines = []
            
        return [inline(self.model, self.admin_site) for inline in inlines]