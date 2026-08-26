# contas/models.py

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

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

    username = None 
    first_name = None
    last_name = None

    nome_completo = models.CharField(_("Nome Completo"), max_length=255)
    email = models.EmailField(_("E-mail"), unique=True) # E-mail agora é o campo de login
    papel = models.CharField(
        max_length=50, 
        choices=Papel.choices, 
        default=Papel.CLIENTE
    )

    mostrar_no_quem_somos = models.BooleanField(
        default=True, 
        verbose_name="Mostrar no Quem Somos",
        help_text="Desmarque para esconder fotógrafos independentes da página oficial da equipe."
    )

    USERNAME_FIELD = 'email'
    
    REQUIRED_FIELDS = ['nome_completo'] 

    def __str__(self):
        return self.nome_completo or self.email

class JornalParceiro(models.Model):
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        limit_choices_to={'papel': Usuario.Papel.FOTOGRAFO},
        related_name='ftp_config'
    )
    nome_jornal = models.CharField(max_length=150, help_text="Ex: Jornal O Globo")
    ftp_host = models.CharField(max_length=200, help_text="Ex: ftp.oglobo.com.br")
    ftp_user = models.CharField(max_length=100)
    ftp_password = models.CharField(max_length=100)
    ftp_pasta = models.CharField(max_length=100, default="/", help_text="Pasta de destino (ex: /public_html/esportes)")
    ativo = models.BooleanField(default=True, help_text="Desmarque para suspender o envio para este jornal temporariamente.")

    def __str__(self):
        return f"{self.nome_jornal} (FTP)"

class MateriaImprensa(models.Model):
    titulo = models.CharField(max_length=255, help_text="Ex: Goleiro Jonathan Queiroz defende pênalti decisivo...")
    veiculo = models.CharField(max_length=150, help_text="Ex: Globo Esporte, Rádio Planalto")
    link = models.URLField(max_length=500)
    data_publicacao = models.DateField()
    
    # 🚀 NOVO CAMPO ADICIONADO AQUI:
    imagem_capa = models.ImageField(upload_to='imprensa_capas/', blank=True, null=True, help_text="Faça o upload da imagem da matéria")
    
    adicionado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-data_publicacao']

    def __str__(self):
        return f"{self.veiculo} - {self.titulo}"
