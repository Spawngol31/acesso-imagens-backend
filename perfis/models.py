from django.db import models

# perfis/models.py
from django.db import models
from contas.models import Usuario
from config.storages import PublicMediaStorage

class PerfilCliente(models.Model):
    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, related_name='perfil_cliente')
    cpf = models.CharField(max_length=14, blank=True, null=True) # Ex: 123.456.789-00
    endereco = models.CharField(max_length=255, blank=True, null=True)
    cep = models.CharField(max_length=9, blank=True, null=True) # Ex: 12345-678

    def __str__(self):
        return self.usuario.nome_completo

class PerfilFotografo(models.Model):
    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, related_name='perfil_fotografo')
    cpf = models.CharField(max_length=14, blank=True, null=True)
    endereco = models.CharField(max_length=255, blank=True, null=True)
    cep = models.CharField(max_length=9, blank=True, null=True)
    foto_perfil = models.ImageField(upload_to='fotografo_perfis/', storage=PublicMediaStorage(), null=True, blank=True)
    especialidade = models.CharField(max_length=100, blank=True, null=True, help_text="Ex: Fotógrafo Esportivo")
    rede_social = models.CharField(max_length=255, blank=True, null=True, help_text="Ex: @seu_instagram")
    registro_profissional = models.CharField(max_length=100, blank=True, null=True)
    numero_registro = models.CharField(max_length=50, blank=True, null=True)
    banco = models.CharField(max_length=100, blank=True, null=True)
    agencia = models.CharField(max_length=20, blank=True, null=True)
    conta = models.CharField(max_length=30, blank=True, null=True)
    chave_pix = models.CharField(max_length=255, blank=True, null=True)
    
    def __str__(self):
        return self.usuario.nome_completo