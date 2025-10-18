from django.db import models
from django.utils.text import slugify
from contas.models import Usuario # Importamos nosso modelo de usuário
from config.storages import PublicMediaStorage, PrivateMediaStorage

class Album(models.Model):
    class Categoria(models.TextChoices):
        ARTES_MARCIAIS = 'ARTES_MARCIAIS', 'Artes Marciais'
        AUTOMOBILISMO = 'AUTOMOBILISMO', 'Automobilismo'
        FUTEBOL = 'FUTEBOL', 'Futebol'
        FUTSAL = 'FUTSAL', 'Futsal'
        BASQUETE = 'BASQUETE', 'Basquete'
        ATLETISMO = 'ATLETISMO', 'Atletismo'
        FUTEBOL_AMERICANO = 'FUTEBOL_AMERICANO', 'Futebol Americano'
        RUGBY = 'RUGBY', 'Rugby'
        NATACAO = 'NATACAO', 'Natação'
        VOLLEYBALL = 'VOLLEYBALL', 'Volleyball'
        OUTRO = 'OUTRO', 'Outro'
    titulo = models.CharField(max_length=200)
    descricao = models.TextField(blank=True, null=True)
    data_evento = models.DateField()
    fotografo = models.ForeignKey(
        Usuario, 
        on_delete=models.CASCADE,
        related_name='albuns',
        # Isso garante que no admin do Django, só aparecerão usuários que são fotógrafos
        limit_choices_to={'papel': Usuario.Papel.FOTOGRAFO} 
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    categoria = models.CharField(max_length=50, choices=Categoria.choices, default=Categoria.OUTRO)
    local = models.CharField(max_length=255, blank=True, null=True)
    is_publico = models.BooleanField(default=True, help_text="Se marcado, o álbum será visível para todos os visitantes.")
    slug = models.SlugField(unique=True, max_length=255, blank=True, help_text="Link personalizado. Ex: 'campeonato-futebol-2025'. Deixe em branco para gerar automaticamente.")
    capa = models.ImageField(upload_to='album_capas/', null=True, blank=True, help_text="Imagem de capa do álbum.", storage=PublicMediaStorage())
    
    def save(self, *args, **kwargs):
        # Gera o slug automaticamente a partir do título se estiver em branco
        if not self.slug:
            self.slug = slugify(self.titulo)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.titulo

    def __str__(self):
        return self.titulo

class Foto(models.Model):
    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name='fotos')
    # O ImageField requer a biblioteca 'Pillow' para funcionar
    imagem = models.ImageField(upload_to='fotos/', storage=PrivateMediaStorage())
    legenda = models.CharField(max_length=255, blank=True, null=True)
    data_upload = models.DateTimeField(auto_now_add=True)
# Usamos DecimalField para evitar erros de arredondamento com dinheiro.
    # `default=10.00` define um preço padrão para novas fotos.
    preco = models.DecimalField(max_digits=10, decimal_places=2, default=10.00)
    rotacao = models.IntegerField(default=0)

    def __str__(self):
        return f"Foto {self.id} do álbum '{self.album.titulo}'"


    def __str__(self):
        return f"Foto {self.id} do álbum '{self.album.titulo}'"
    
    # Este campo armazenará a miniatura processada.
    # `blank=True` é essencial, pois ele será preenchido DEPOIS do upload inicial.
    miniatura_marca_dagua = models.ImageField(upload_to='miniaturas/', blank=True, null=True, storage=PublicMediaStorage())

    legenda = models.CharField(max_length=255, blank=True, null=True)
    data_upload = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Foto {self.id} do álbum '{self.album.titulo}'"

class Video(models.Model):
    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name='videos')
    titulo = models.CharField(max_length=255)
    # FileField é usado para qualquer tipo de arquivo, não apenas imagens
    arquivo_video = models.FileField(upload_to='videos/', storage=PrivateMediaStorage())
    # Miniatura para exibir na galeria
    miniatura = models.ImageField(upload_to='videos_thumbnails/', help_text="Thumbnail de pré-visualização para o vídeo.", blank=True, null=True, storage=PublicMediaStorage())
    preco = models.DecimalField(max_digits=10, decimal_places=2, default=25.00)
    data_upload = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.titulo
    
class FaceIndexada(models.Model):
    foto = models.ForeignKey(Foto, on_delete=models.CASCADE, related_name='faces_indexadas')
    rekognition_face_id = models.CharField(max_length=255, unique=True, db_index=True)
    data_indexacao = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Face {self.rekognition_face_id} em Foto {self.foto.id}"
    
