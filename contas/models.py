# contas/models.py

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _ # Importação necessária

class Usuario(AbstractUser):
    class Papel(models.TextChoices):
        CLIENTE = 'CLIENTE', 'Cliente'
        FOTOGRAFO = 'FOTOGRAFO', 'Fotógrafo'
        ADMIN = 'ADMIN', 'Administrador'

    # Removemos o campo 'username'
    username = None 
    first_name = None
    last_name = None

    # Novos campos
    nome_completo = models.CharField(_("Nome Completo"), max_length=255)
    email = models.EmailField(_("E-mail"), unique=True) # E-mail agora é o campo de login
    papel = models.CharField(
        max_length=50, 
        choices=Papel.choices, 
        default=Papel.CLIENTE
    )

    USERNAME_FIELD = 'email'
    
    # --- CORREÇÃO AQUI ---
    # O email (USERNAME_FIELD) não pode estar nos campos obrigatórios
    REQUIRED_FIELDS = ['nome_completo'] 

    def __str__(self):
        return self.email