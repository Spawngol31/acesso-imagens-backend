import boto3
import uuid
from django.db.models import Q
from django.core.files.base import ContentFile
from django.conf import settings
from rest_framework import generics, viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action
from decimal import Decimal, InvalidOperation
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from PIL import Image, ImageOps
from io import BytesIO

# Importa as tasks
from .tasks import distribuir_foto_para_ftps, distribuir_foto_temporaria_ftp, processar_preview_video

# Importa os modelos e serializers
from .models import Album, Foto, Video, FaceIndexada
from .serializers import (
    AlbumSerializer, 
    AlbumDetailSerializer, 
    FotoSerializer,
    FotoUploadSerializer,
    VideoUploadSerializer,
    AlbumDashboardSerializer,
    FotoDashboardSerializer,
    VideoDashboardSerializer
)

# Permissões do app contas
from contas.permissions import IsFotografoOrAdmin, IsAdminUser
from contas.models import Usuario

# =========================================================
# --- VIEWS PÚBLICAS (PARA OS CLIENTES) ---
# =========================================================

class AlbumListView(generics.ListAPIView):
    queryset = Album.objects.filter(
        is_publico=True, 
        is_arquivado=False
    ).select_related('fotografo').order_by('-data_evento')
    
    serializer_class = AlbumSerializer
    permission_classes = [AllowAny]

class AlbumDetailView(generics.RetrieveAPIView):
    serializer_class = AlbumDetailSerializer
    permission_classes = [AllowAny]
    lookup_field = 'id'

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated:
            if user.papel == Usuario.Papel.ADMIN:
                return Album.objects.all()
            papeis_equipe = [
                Usuario.Papel.FOTOGRAFO, Usuario.Papel.JORNALISTA, 
                Usuario.Papel.ASSESSOR_IMPRENSA, Usuario.Papel.ASSESSOR_COMUNICACAO, 
                Usuario.Papel.VIDEOMAKER, Usuario.Papel.CRIADOR_CONTEUDO
            ]
            if user.papel in papeis_equipe:
                return Album.objects.filter(Q(is_publico=True, is_arquivado=False) | Q(fotografo=user))
        return Album.objects.filter(is_publico=True, is_arquivado=False)

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response

class StatusFilaProcessamentoView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        fotos_na_fila = Foto.objects.filter(
            Q(miniatura_marca_dagua='') | Q(miniatura_marca_dagua__isnull=True)
        ).count()
        return Response({'fotos_na_fila': fotos_na_fila})

class BuscaFacialView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request, *args, **kwargs):
        imagem_referencia = request.FILES.get('imagem_referencia')
        album_id = request.data.get('album_id')
        
        if not imagem_referencia: 
            return Response({"error": "Nenhuma imagem."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 1. LER E COMPACTAR A IMAGEM UMA SÓ VEZ
            image_bytes = imagem_referencia.read()
            if len(image_bytes) > 5 * 1024 * 1024:
                img = Image.open(BytesIO(image_bytes))
                img = ImageOps.exif_transpose(img)
                img.thumbnail((1080, 1080), Image.Resampling.LANCZOS)
                buffer = BytesIO()
                img.convert("RGB").save(buffer, format='JPEG', quality=85)
                image_bytes = buffer.getvalue() # Salva a imagem processada

            # 2. CHAMADA AO REKOGNITION (Usando os bytes processados)
            rekognition_client = boto3.client('rekognition', region_name=settings.AWS_REKOGNITION_REGION_NAME)
            response = rekognition_client.search_faces_by_image(
                CollectionId=settings.AWS_REKOGNITION_COLLECTION_ID,
                Image={'Bytes': image_bytes}, # <--- CORREÇÃO AQUI
                MaxFaces=5, FaceMatchThreshold=95
            )
            
            face_matches = response.get('FaceMatches', [])
            if not face_matches: 
                return Response([], status=status.HTTP_200_OK)

            # 3. PEGA OS IDS RETORNADOS E BUSCA NO BANCO
            matched_face_ids = [match['Face']['FaceId'] for match in face_matches]
            fotos_encontradas_ids = FaceIndexada.objects.filter(rekognition_face_id__in=matched_face_ids).values_list('foto_id', flat=True).distinct()
            
            # 4. AQUI APLICAMOS O FILTRO DE ÁLBUM!
            if album_id:
                # Se enviou album_id, filtra apenas as fotos desse álbum
                fotos = Foto.objects.filter(
                    id__in=fotos_encontradas_ids, 
                    album_id=album_id, # <--- FILTRA AQUI
                    is_arquivado=False
                )
            else:
                # Se não enviou (Busca Global), filtra no site todo (álbuns públicos e não arquivados)
                fotos = Foto.objects.filter(
                    id__in=fotos_encontradas_ids, 
                    is_arquivado=False, 
                    album__is_arquivado=False, 
                    album__is_publico=True
                )
            
            serializer = FotoSerializer(fotos, many=True, context={'request': request})
            return Response(serializer.data)
            
        except Exception as e:
            print(f"Erro na busca facial: {e}")
            return Response({"error": "Ocorreu um erro durante a busca facial."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
# =========================================================================================
# 🚀 LÓGICA DE UPLOAD REVOLUCIONADA (Site vs FTP)
# =========================================================================================

class FotoUploadView(APIView):
    permission_classes = [IsAuthenticated, IsFotografoOrAdmin]

    def post(self, request, *args, **kwargs):
        destino = request.data.get('destino_upload', 'site')
        jornais_string = request.data.get('jornais')
        imagem_file = request.FILES.get('imagem')
        
        # 1. Coleta os metadados IPTC enviados pelo React
        metadados = {
            'titulo': request.data.get('ftp_titulo', ''),
            'data': request.data.get('ftp_data', ''),
            'local': request.data.get('ftp_local', ''),
            'legenda': request.data.get('ftp_legenda', ''),
            'creditos': request.data.get('ftp_creditos', '')
        }
        
        jornais_ids = []
        if jornais_string:
            jornais_ids = [int(id_str.strip()) for id_str in jornais_string.split(',') if id_str.strip().isdigit()]

        # --- CENÁRIO 1: APENAS SITE ou AMBOS ---
        # Se for para o site, temos de validar o preço e gravar no banco de dados.
        if destino in ['site', 'ambos']:
            serializer = FotoUploadSerializer(data=request.data, context={'request': request})
            if serializer.is_valid():
                foto = serializer.save()
                
                # Se for "ambos", dispara o FTP usando a foto salva
                if destino == 'ambos' and jornais_ids:
                    print(f"--- Disparando FTP (Ambos) para {jornais_ids} com metadados ---")
                    # ⚠️ ATENÇÃO: Passamos os 'metadados' como terceiro argumento para o celery
                    distribuir_foto_para_ftps.delay(foto.id, jornais_ids, metadados)
                    
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # --- CENÁRIO 2: APENAS FTP (Não salva no Site/Banco de Dados) ---
        elif destino == 'ftp':
            if not jornais_ids or not imagem_file:
                return Response({'error': 'Faltam jornais ou imagem para envio FTP.'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                # Upload direto para uma pasta temporária na AWS S3
                s3_client = boto3.client(
                    's3', 
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID, 
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY, 
                    region_name=settings.AWS_S3_REGION_NAME,
                    config=boto3.session.Config(signature_version='s3v4')
                )
                
                temp_key = f"tmp_ftp/{uuid.uuid4().hex}_{imagem_file.name}"
                s3_client.upload_fileobj(imagem_file, settings.AWS_STORAGE_BUCKET_NAME, temp_key)
                
                print(f"--- Disparando FTP Temporário para {jornais_ids} com metadados ---")
                
                # 🚀 AGORA SIM! Enviamos a ordem real para o Celery fazer o trabalho em segundo plano:
                distribuir_foto_temporaria_ftp.delay(temp_key, jornais_ids, metadados)

                return Response({'status': 'Foto enviada direto para os jornais com sucesso!'}, status=status.HTTP_200_OK)
                
            except Exception as e:
                print(f"Erro no upload temporário FTP: {e}")
                return Response({'error': 'Erro ao processar arquivo FTP.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# =========================================================================================

class VideoUploadDashboardView(generics.CreateAPIView):
    queryset = Video.objects.all()
    serializer_class = VideoUploadSerializer
    permission_classes = [IsAuthenticated, IsFotografoOrAdmin]

    def perform_create(self, serializer):
        # 1. O Django salva o vídeo original no banco de dados.
        # Não precisamos mais chamar o .delay() aqui porque o signals.py já fará isso!
        serializer.save()
        
class AlbumViewSet(viewsets.ModelViewSet):
    serializer_class = AlbumDashboardSerializer
    permission_classes = [IsAuthenticated, IsFotografoOrAdmin]

    def get_queryset(self):
        if self.request.user.papel == 'ADMIN': return Album.objects.all()
        return Album.objects.filter(fotografo=self.request.user)

    def perform_create(self, serializer):
        if self.request.user.papel == Usuario.Papel.FOTOGRAFO:
            serializer.save(fotografo=self.request.user)
        elif self.request.user.papel == Usuario.Papel.ADMIN:
            serializer.save()

    @action(detail=True, methods=['post'])
    def arquivar(self, request, pk=None):
        album = self.get_object()
        album.is_arquivado = True
        album.save()
        return Response({'status': 'álbum arquivado'})

    @action(detail=True, methods=['post'])
    def desarquivar(self, request, pk=None):
        album = self.get_object()
        album.is_arquivado = False
        album.save()
        return Response({'status': 'álbum desarquivado'})

    @action(detail=True, methods=['post'])
    def bulk_update_photos(self, request, pk=None):
        album = self.get_object()
        new_price_str = request.data.get('preco')
        if new_price_str is None: return Response({'error': 'Preço não fornecido.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            new_price = Decimal(new_price_str)
            if new_price < 0: raise InvalidOperation
        except InvalidOperation:
             return Response({'error': 'Preço inválido.'}, status=status.HTTP_400_BAD_REQUEST)
        
        count = album.fotos.all().update(preco=new_price)
        return Response({'status': f'{count} fotos atualizadas com sucesso para R$ {new_price:.2f}'})

    @action(detail=True, methods=['post'])
    def bulk_update_videos(self, request, pk=None):
        album = self.get_object()
        new_price_str = request.data.get('preco')
        if new_price_str is None: return Response({'error': 'Preço não fornecido.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            new_price = Decimal(new_price_str)
            if new_price < 0: raise InvalidOperation
        except InvalidOperation:
             return Response({'error': 'Preço inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        count = album.videos.all().update(preco=new_price)
        return Response({'status': f'{count} vídeos atualizados com sucesso para R$ {new_price:.2f}'})
    
    @action(detail=True, methods=['post'])
    def definir_capa(self, request, pk=None):
        album = self.get_object()
        foto_id = request.data.get('foto_id')
        if not foto_id: return Response({'error': 'ID da foto não fornecido.'}, status=status.HTTP_400_BAD_REQUEST)
            
        foto = get_object_or_404(Foto, id=foto_id, album=album)
        if not foto.miniatura_marca_dagua:
            return Response({'error': 'A foto ainda está sendo processada. Aguarde uns instantes.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            nome_arquivo = f"capa_album_{album.id}_foto_{foto.id}.jpg"
            album.capa.save(nome_arquivo, ContentFile(foto.miniatura_marca_dagua.read()), save=True)
            return Response({'status': 'Capa do álbum atualizada com sucesso!'})
        except Exception as e:
            return Response({'error': 'Erro ao processar a imagem para a capa.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class FotoViewSet(viewsets.ModelViewSet):
    serializer_class = FotoDashboardSerializer
    permission_classes = [IsAuthenticated, IsFotografoOrAdmin]

    def get_queryset(self):
        if self.request.user.papel == 'ADMIN': return Foto.objects.all()
        return Foto.objects.filter(album__fotografo=self.request.user)
    
    @action(detail=True, methods=['post'])
    def arquivar(self, request, pk=None):
        foto = self.get_object()
        foto.is_arquivado = True
        foto.save()
        return Response({'status': 'foto arquivada'})

    @action(detail=True, methods=['post'])
    def desarquivar(self, request, pk=None):
        foto = self.get_object()
        foto.is_arquivado = False
        foto.save()
        return Response({'status': 'foto desarquivada'})

    # =========================================================
    # NOVA OPÇÃO: BAIXAR FOTO ORIGINAL
    # =========================================================
    @action(detail=True, methods=['get'])
    def baixar_original(self, request, pk=None):
        foto = self.get_object() 
        
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        
        # 1. Pega o nome do arquivo salvo no banco de dados
        caminho_banco = foto.imagem.name
        nome_arquivo = caminho_banco.split('/')[-1]
        
        # 2. Descobre se o seu S3 usa uma pasta raiz (ex: 'media') e ajusta a chave
        aws_location = getattr(settings, 'AWS_LOCATION', '').strip('/')
        if aws_location:
            caminho_s3 = f"{aws_location}/{caminho_banco}".replace('//', '/')
        else:
            caminho_s3 = caminho_banco
        
        # Gera o link seguro direto da AWS que força o download
        url = s3_client.generate_presigned_url(
            ClientMethod='get_object',
            Params={
                'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                'Key': caminho_s3, # Usa o caminho corrigido
                'ResponseContentDisposition': f'attachment; filename="{nome_arquivo}"'
            },
            ExpiresIn=3600
        )
        
        return Response({'url_download': url})
    

class VideoViewSet(viewsets.ModelViewSet):
    serializer_class = VideoDashboardSerializer
    permission_classes = [IsAuthenticated, IsFotografoOrAdmin]

    def get_queryset(self):
        if self.request.user.papel == 'ADMIN': return Video.objects.all()
        return Video.objects.filter(album__fotografo=self.request.user)
    
def album_share_preview(request, pk):
    album = get_object_or_404(Album, pk=pk)
    base_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173').rstrip('/')
    frontend_url = f"{base_url}/album/{album.id}"
    
    image_url = ""
    if album.capa:
        image_url = album.capa.url
        if not image_url.startswith('http'): image_url = request.build_absolute_uri(image_url)
        if image_url.startswith('http://'): image_url = image_url.replace('http://', 'https://')
        if '?' in image_url: image_url = image_url.split('?')[0]

    html = f"""
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="UTF-8">
        <title>{album.titulo}</title>
        <meta property="og:type" content="website">
        <meta property="og:url" content="{frontend_url}">
        <meta property="og:title" content="{album.titulo} | Acesso Imagens">
        <meta property="og:description" content="{album.descricao or 'Confira as fotos exclusivas deste evento!'}">
        <meta property="og:image" content="{image_url}">
        <meta property="og:image:secure_url" content="{image_url}">
        <meta property="og:image:type" content="image/jpeg">
        <link rel="image_src" href="{image_url}">
        <script>window.location.replace("{frontend_url}");</script>
    </head>
    <body style="background-color: #f2e6f2; text-align: center; padding-top: 50px; font-family: sans-serif;">
        <p style="color: #6c0464;">Redirecionando você para o álbum...</p>
    </body>
    </html>
    """
    return HttpResponse(html)