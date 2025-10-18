# galeria/serializers.py

import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from rest_framework import serializers
from .models import Foto, Album, Video
from contas.models import Usuario

# --- SERIALIZERS DE EXIBIÇÃO PARA CLIENTES ---

class FotoSerializer(serializers.ModelSerializer):
    # O DRF agora irá gerar a URL pública automaticamente a partir do campo
    imagem_url = serializers.URLField(source='miniatura_marca_dagua.url', read_only=True)

    class Meta:
        model = Foto
        fields = ['id', 'legenda', 'preco', 'imagem_url', 'rotacao']

class VideoSerializer(serializers.ModelSerializer):
    miniatura_url = serializers.URLField(source='miniatura.url', read_only=True)

    class Meta:
        model = Video
        fields = ['id', 'titulo', 'preco', 'miniatura_url']

class AlbumSerializer(serializers.ModelSerializer):
    fotografo = serializers.StringRelatedField()
    fotos_count = serializers.IntegerField(source='fotos.count', read_only=True)
    capa_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Album
        fields = ['id', 'titulo', 'descricao', 'data_evento', 'fotografo', 'fotos_count', 'slug', 'capa_url']

    # --- SUBSTITUA ESTA FUNÇÃO ---
    def get_capa_url(self, obj):
        # 1. Primeiro, verifica se o campo 'capa' e o nome do ficheiro existem.
        if not obj.capa or not obj.capa.name:
            return None # Retorna nulo se não houver capa, em vez de crashar.
        
        # 2. O resto da lógica para gerar a URL assinada continua a mesma.
        key = obj.capa.name.lstrip('/')
        
        location_prefix = getattr(settings, 'AWS_LOCATION', '')
        if location_prefix and not key.startswith(f"{location_prefix}/"):
            key = f"{location_prefix}/{key}"
        
        try:
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_S3_REGION_NAME,
                config=boto3.session.Config(signature_version='s3v4')
            )
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': settings.AWS_STORAGE_BUCKET_NAME, 'Key': key},
                ExpiresIn=3600
            )
            return url
        except ClientError:
            return None

class AlbumDetailSerializer(AlbumSerializer):
    fotos = FotoSerializer(many=True, read_only=True)
    videos = VideoSerializer(many=True, read_only=True)
    
    class Meta(AlbumSerializer.Meta):
        fields = AlbumSerializer.Meta.fields + ['fotos', 'videos']


# --- SERIALIZERS PARA UPLOAD E DASHBOARD ---

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