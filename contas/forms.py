# contas/forms.py

from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import Usuario

class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Usuario
        # --- CORREÇÃO AQUI: 'username' removido ---
        fields = ('email', 'nome_completo', 'papel')

class CustomUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = Usuario
        # --- CORREÇÃO AQUI: 'username' removido ---
        fields = ('email', 'nome_completo', 'papel', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')