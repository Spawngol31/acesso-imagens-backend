# galeria/models.py

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
        limit_choices_to={'papel': Usuario.Papel.FOTOGRAFO} 
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    categoria = models.CharField(max_length=50, choices=Categoria.choices, default=Categoria.OUTRO)
    local = models.CharField(max_length=255, blank=True, null=True)
    is_publico = models.BooleanField(default=True, help_text="Se marcado, o álbum será visível para todos os visitantes.")
    slug = models.SlugField(unique=True, max_length=255, blank=True, help_text="Link personalizado. Deixe em branco para gerar automaticamente.")
    capa = models.ImageField(upload_to='album_capas/', null=True, blank=True, help_text="Imagem de capa do álbum.", storage=PublicMediaStorage())
    is_arquivado = models.BooleanField(default=False, help_text="Se marcado, o álbum não será visível no site público.")

    def save(self, *args, **kwargs):
        # --- LÓGICA DE SLUG ROBUSTA (À PROVA DE ERROS) ---
        if not self.slug:
            original_slug = slugify(self.titulo)
            queryset = Album.objects.all()
            
            if self.pk:
                queryset = queryset.exclude(pk=self.pk)

            new_slug = original_slug
            counter = 1
            while queryset.filter(slug=new_slug).exists():
                new_slug = f'{original_slug}-{counter}'
                counter += 1
            
            self.slug = new_slug
            
        super().save(*args, **kwargs)

    def __str__(self):
        return self.titulo
    # O __str__ duplicado foi removido

class Foto(models.Model):
    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name='fotos')
    imagem = models.ImageField(upload_to='fotos/', storage=PrivateMediaStorage())
    legenda = models.CharField(max_length=255, blank=True, null=True)
    data_upload = models.DateTimeField(auto_now_add=True)
    preco = models.DecimalField(max_digits=10, decimal_places=2, default=10.00)
    rotacao = models.IntegerField(default=0)
    miniatura_marca_dagua = models.ImageField(upload_to='miniaturas/', blank=True, null=True, storage=PublicMediaStorage())
    is_arquivado = models.BooleanField(default=False, help_text="Se marcado, a foto não será visível no site público.")

    # Os campos duplicados 'legenda' e 'data_upload' foram removidos
    
    def __str__(self):
        return f"Foto {self.id} do álbum '{self.album.titulo}'"
    # O __str__ duplicado foi removido

class Video(models.Model):
    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name='videos')
    titulo = models.CharField(max_length=255)
    arquivo_video = models.FileField(upload_to='videos/', storage=PrivateMediaStorage())
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