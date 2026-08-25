# galeria/serializers.py

import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from rest_framework import serializers
from .models import Album, Foto, Video, FaceIndexada, Avaliacao
from contas.models import Usuario

# --- SERIALIZER DE FOTO (ATUALIZADO PARA FOTOS NÃO IDENTIFICADAS) ---
class FotoSerializer(serializers.ModelSerializer):
    imagem_url = serializers.SerializerMethodField()
    tem_rostos = serializers.SerializerMethodField() # 🚀 NOVO: Campo calculado para a busca

    class Meta:
        model = Foto
        # 🚀 NOVO: 'tem_rostos' adicionado ao final da lista
        fields = ['id', 'legenda', 'preco', 'imagem_url', 'rotacao', 'is_arquivado', 'categoria', 'tem_rostos']

    def get_imagem_url(self, obj):
        # Lógica defensiva:
        # 1. Verifica se a miniatura (que é pública) existe
        if obj.miniatura_marca_dagua and obj.miniatura_marca_dagua.name:
            # 2. Se sim, retorna a sua URL pública direta. É rápido.
            return obj.miniatura_marca_dagua.url
        
        # 3. Se a miniatura ainda não foi processada (Celery a correr),
        #    retornamos None para não "crashar" a API.
        return None

    # 🚀 NOVO: A mágica acontece aqui usando o 'related_name' do seu models.py
    def get_tem_rostos(self, obj):
        # Retorna True se a foto tiver rostos indexados pelo AWS Rekognition, ou False se não tiver
        return obj.faces_indexadas.exists()

# --- SERIALIZER DE VÍDEO (CORRIGIDO) ---
class VideoSerializer(serializers.ModelSerializer):
    # A miniatura e o preview do vídeo são públicos
    miniatura_url = serializers.SerializerMethodField()
    arquivo_preview_url = serializers.SerializerMethodField() # <-- ADICIONADO

    class Meta:
        model = Video
        # <-- ADICIONADO 'arquivo_preview_url' na lista
        fields = ['id', 'titulo', 'preco', 'miniatura_url', 'arquivo_preview_url', 'categoria'] 

    def get_miniatura_url(self, obj):
        if obj.miniatura and obj.miniatura.name:
            return obj.miniatura.url
        return None

    # <-- NOVA FUNÇÃO PARA ENVIAR O VÍDEO DE 10s
    def get_arquivo_preview_url(self, obj):
        if obj.arquivo_preview and obj.arquivo_preview.name:
            return obj.arquivo_preview.url
        return None

# --- SERIALIZER DE ÁLBUM (COM A LÓGICA CORRETA) ---
class AlbumSerializer(serializers.ModelSerializer):
    fotografo_nome = serializers.SerializerMethodField()
    fotografo = serializers.StringRelatedField()
    fotos_count = serializers.IntegerField(source='fotos.count', read_only=True)
    capa_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Album
        fields = ['id', 'titulo', 'descricao', 'data_evento', 'fotografo', 'fotos_count', 'slug', 'local', 'fotografo_nome', 'capa_url', 'is_arquivado',
                  'qtd_desconto_1', 'pct_desconto_1',
                  'qtd_desconto_2', 'pct_desconto_2',
                  'qtd_desconto_3', 'pct_desconto_3'
                  ] # Adicionámos 'is_arquivado'

    def get_fotografo_nome(self, obj):
        if obj.fotografo:
            # Agora usamos o campo exato que você criou no seu models.py!
            nome = getattr(obj.fotografo, 'nome_completo', '')
            
            # Se tiver nome_completo, envia ele
            if nome:
                return nome
            
            # Se por algum motivo estiver vazio, envia o e-mail como segurança
            return getattr(obj.fotografo, 'email', '')
            
        return ""        

    def get_capa_url(self, obj):
        # A capa do álbum também é pública
        if obj.capa and obj.capa.name:
            return obj.capa.url
        return None # Retorna nulo se não houver capa, em vez de crashar

# --- SERIALIZER DE DETALHES DO ÁLBUM (CORRETO) ---
class AlbumDetailSerializer(AlbumSerializer):
    fotos = serializers.SerializerMethodField()
    videos = VideoSerializer(many=True, read_only=True) # Assumindo que vídeos não são arquivados
    
    class Meta(AlbumSerializer.Meta):
        fields = AlbumSerializer.Meta.fields + ['fotos', 'videos']

    def get_fotos(self, obj):
        # 1. Pega o 'request' do contexto do serializer
        request = self.context.get('request')
        
        # 2. Define o queryset base (todas as fotos do álbum)
        queryset = obj.fotos.all().order_by('id')
        
        # 3. Verifica se o utilizador está logado e é o dono do álbum (ou admin)
        is_owner_or_admin = False
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            if request.user == obj.fotografo or request.user.papel == Usuario.Papel.ADMIN:
                is_owner_or_admin = True

        # 4. Se NÃO for o dono, filtra as fotos arquivadas
        if not is_owner_or_admin:
            queryset = queryset.filter(is_arquivado=False)
        
        # 5. Retorna os dados
        return FotoSerializer(queryset, many=True, context=self.context).data

# --- SERIALIZERS PARA UPLOAD E DASHBOARD (CORRETOS) ---
# (Estes são usados pelo seu painel, não pelo público)
class FotoUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Foto
        fields = ['album', 'imagem', 'legenda', 'preco', 'categoria']

class VideoUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Video
        fields = ['album', 'titulo', 'preco', 'arquivo_video', 'categoria']

    # --- CORREÇÃO 2: GERAR TÍTULO AUTOMÁTICO ---
    def create(self, validated_data):
        # Se o fotógrafo não preencher o título, o sistema cria um automático
        if not validated_data.get('titulo'):
            arquivo = validated_data.get('arquivo_video')
            if arquivo:
                # Pega o nome do arquivo original (ex: 'casamento_01.mp4' vira 'casamento_01')
                nome_sem_extensao = arquivo.name.split('/')[-1].split('.')[0]
                validated_data['titulo'] = nome_sem_extensao
            else:
                validated_data['titulo'] = "Vídeo sem título"
                
        return super().create(validated_data)

class AlbumDashboardSerializer(serializers.ModelSerializer):
    qtd_vendida = serializers.IntegerField(read_only=True, default=0)
    total_arrecadado = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True, default=0.00)
    class Meta:
        model = Album
        fields = [
            'id', 'titulo', 'descricao', 'data_evento', 'categoria', 
            'local', 'is_publico', 'slug', 'fotografo',
            'capa', 'is_arquivado', 'qtd_vendida', 'total_arrecadado',
            'qtd_desconto_1', 'pct_desconto_1',
            'qtd_desconto_2', 'pct_desconto_2',
            'qtd_desconto_3', 'pct_desconto_3'
        ]
        read_only_fields = ['slug', 'fotografo']

class FotoDashboardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Foto
        fields = [
            'id', 'album', 'legenda', 'preco', 
            'imagem', 'miniatura_marca_dagua',
            'rotacao', 'is_arquivado', 'categoria'
        ]
        read_only_fields = ['id', 'album', 'imagem', 'miniatura_marca_dagua']

class VideoDashboardSerializer(serializers.ModelSerializer):
    # --- CORREÇÃO 1: ADICIONANDO AS URLs ABSOLUTAS NO DASHBOARD ---
    miniatura_url = serializers.SerializerMethodField()
    arquivo_preview_url = serializers.SerializerMethodField()

    class Meta:
        model = Video
        # Adicionamos 'miniatura_url' e 'arquivo_preview_url' aqui
        fields = ['id', 'album', 'titulo', 'arquivo_video', 'arquivo_preview_url', 'miniatura_url', 'preco', 'data_upload', 'categoria']
        
    def get_miniatura_url(self, obj):
        if obj.miniatura and obj.miniatura.name:
            return obj.miniatura.url
        return None

    def get_arquivo_preview_url(self, obj):
        if obj.arquivo_preview and obj.arquivo_preview.name:
            return obj.arquivo_preview.url
        return None

class AvaliacaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Avaliacao
        fields = '__all__'