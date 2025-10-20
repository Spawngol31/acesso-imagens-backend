# galeria/serializers.py

# Não precisamos mais do boto3 aqui para os serializers públicos
from django.conf import settings
from rest_framework import serializers
from .models import Foto, Album, Video
from contas.models import Usuario

# --- SERIALIZER DE FOTO (COM A LÓGICA CORRETA) ---
class FotoSerializer(serializers.ModelSerializer):
    imagem_url = serializers.SerializerMethodField()

    class Meta:
        model = Foto
        fields = ['id', 'legenda', 'preco', 'imagem_url', 'rotacao']

    def get_imagem_url(self, obj):
        # Lógica defensiva:
        # 1. Verifica se a miniatura (que é pública) existe
        if obj.miniatura_marca_dagua and obj.miniatura_marca_dagua.name:
            # 2. Se sim, retorna a sua URL pública direta. É rápido.
            return obj.miniatura_marca_dagua.url
        
        # 3. Se a miniatura ainda não foi processada (Celery a correr),
        #    retornamos None para não "crashar" a API. O frontend
        #    deve ser capaz de lidar com uma URL nula (ex: mostrar um placeholder).
        return None

# --- SERIALIZER DE VÍDEO (CORRETO) ---
class VideoSerializer(serializers.ModelSerializer):
    # A miniatura do vídeo também é pública
    miniatura_url = serializers.SerializerMethodField()

    class Meta:
        model = Video
        fields = ['id', 'titulo', 'preco', 'miniatura_url']

    def get_miniatura_url(self, obj):
        if obj.miniatura and obj.miniatura.name:
            return obj.miniatura.url
        return None

# --- SERIALIZER DE ÁLBUM (COM A LÓGICA CORRETA) ---
class AlbumSerializer(serializers.ModelSerializer):
    fotografo = serializers.StringRelatedField()
    fotos_count = serializers.IntegerField(source='fotos.count', read_only=True)
    capa_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Album
        fields = ['id', 'titulo', 'descricao', 'data_evento', 'fotografo', 'fotos_count', 'slug', 'capa_url']

    def get_capa_url(self, obj):
        # A capa do álbum também é pública
        if obj.capa and obj.capa.name:
            return obj.capa.url
        return None # Retorna nulo se não houver capa, em vez de crashar

# --- SERIALIZER DE DETALHES DO ÁLBUM (CORRETO) ---
class AlbumDetailSerializer(AlbumSerializer):
    fotos = FotoSerializer(many=True, read_only=True)
    videos = VideoSerializer(many=True, read_only=True)
    
    class Meta(AlbumSerializer.Meta):
        fields = AlbumSerializer.Meta.fields + ['fotos', 'videos']

# --- SERIALIZERS PARA UPLOAD E DASHBOARD (CORRETOS) ---
# (Estes são usados pelo seu painel, não pelo público)
class FotoUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Foto
        fields = ['album', 'imagem', 'legenda', 'preco']

class VideoUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Video
        fields = ['album', 'titulo', 'preco', 'arquivo_video']

class AlbumDashboardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Album
        fields = [
            'id', 'titulo', 'descricao', 'data_evento', 'categoria', 
            'local', 'is_publico', 'slug', 'fotografo',
            'capa'
        ]
        read_only_fields = ['slug', 'fotografo']

class FotoDashboardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Foto
        fields = [
            'id', 'album', 'legenda', 'preco', 
            'imagem', 'miniatura_marca_dagua',
            'rotacao'
        ]
        read_only_fields = ['id', 'album', 'imagem', 'miniatura_marca_dagua']

class VideoDashboardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Video
        fields = [
            'id', 'album', 'titulo', 'preco', 
            'arquivo_video', 'miniatura',
        ]
        read_only_fields = ['id', 'album', 'arquivo_video', 'miniatura']