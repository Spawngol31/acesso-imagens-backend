from django.db import models
from django.contrib.auth.models import AbstractUser

class Usuario(AbstractUser):
    """
    Modelo de usuário personalizado que inclui os diferentes papéis no sistema.
    """
    class Papel(models.TextChoices):
        CLIENTE = 'CLIENTE', 'Cliente'
        FOTOGRAFO = 'FOTOGRAFO', 'Fotógrafo'
        ADMIN = 'ADMIN', 'Administrador'

    # Remove campos não necessários do AbstractUser padrão
    first_name = None
    last_name = None

    # Novos campos
    nome_completo = models.CharField(max_length=255, verbose_name="Nome Completo")
    email = models.EmailField(unique=True, verbose_name="E-mail")
    papel = models.CharField(max_length=50, choices=Papel.choices, default=Papel.CLIENTE)

    # Configura o campo de login para ser o email
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'nome_completo']

    def __str__(self):
        return self.email