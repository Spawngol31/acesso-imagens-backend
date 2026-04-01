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
        
        # --- MUDANÇA AQUI ---
        # Criamos a lista de papéis que dão direito a ter um "PerfilFotografo" 
        # (que agora funciona como um perfil de Colaborador Geral)
        papeis_da_equipe = [
            Usuario.Papel.FOTOGRAFO,
            Usuario.Papel.JORNALISTA,
            Usuario.Papel.ASSESSOR_IMPRENSA,
            Usuario.Papel.ASSESSOR_COMUNICACAO,
            Usuario.Papel.VIDEOMAKER,
            Usuario.Papel.CRIADOR_CONTEUDO
        ]

        if obj.papel == Usuario.Papel.CLIENTE:
            return [PerfilClienteInline(self.model, self.admin_site)]
        elif obj.papel in papeis_da_equipe:
            return [PerfilFotografoInline(self.model, self.admin_site)]
        
        # Se for Admin, não mostra inlines
        return []