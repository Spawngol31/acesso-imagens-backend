# contas/models.py

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _ # Importação necessária

class Usuario(AbstractUser):
    class Papel(models.TextChoices):
        CLIENTE = 'CLIENTE', 'Cliente'
        FOTOGRAFO = 'FOTOGRAFO', 'Fotógrafo'
        ADMIN = 'ADMIN', 'Administrador'
        JORNALISTA = 'JORNALISTA', 'Jornalista'
        ASSESSOR_IMPRENSA = 'ASSESSOR_IMPRENSA', 'Assessor de Imprensa'
        ASSESSOR_COMUNICACAO = 'ASSESSOR_COMUNICACAO', 'Assessor de Comunicação'
        VIDEOMAKER = 'VIDEOMAKER', 'Videomaker'
        CRIADOR_CONTEUDO = 'CRIADOR_CONTEUDO', 'Criador de Conteúdo'

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
        # Agora o "nome oficial" do utilizador no sistema será o Nome Completo
        # Colocamos o "or self.email" como segurança caso o nome esteja vazio
        return self.nome_completo or self.email