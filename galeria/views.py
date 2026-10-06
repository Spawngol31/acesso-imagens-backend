# galeria/views.py

import boto3
import uuid
import os
from PIL import Image, ImageOps
from io import BytesIO
from .models import Album, Foto, Video
from django.db.models import Sum, Count, Q, Value
from django.db.models.functions import Coalesce
from django.core.files.base import ContentFile
from django.conf import settings
from rest_framework import generics, viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.decorators import action, api_view, permission_classes
from decimal import Decimal, InvalidOperation
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from .tasks import apagar_midias_antigas_task

# Importa as tasks
from .tasks import distribuir_foto_para_ftps, distribuir_foto_temporaria_ftp, processar_preview_video

# Importa os modelos e serializers
from .models import Album, Foto, Video, FaceIndexada, Avaliacao
from .serializers import (
    AlbumSerializer, 
    AlbumDetailSerializer, 
    FotoSerializer,
    FotoUploadSerializer,
    VideoUploadSerializer,
    AlbumDashboardSerializer,
    FotoDashboardSerializer,
    VideoDashboardSerializer,
    AvaliacaoSerializer
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
                Image={'Bytes': image_bytes},
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
                fotos = Foto.objects.filter(
                    id__in=fotos_encontradas_ids, 
                    album_id=album_id,
                    is_arquivado=False
                )
            else:
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
# 🚀 DIRECT-TO-S3 (FASE 2)
# =========================================================================================

class GeneratePresignedUrlView(APIView):
    """
    Gera a URL segura para o React fazer upload direto para a AWS/Cloudflare.
    Assim o seu servidor Hetzner não recebe os arquivos pesados.
    """
    permission_classes = [IsAuthenticated, IsFotografoOrAdmin]

    def post(self, request):
        file_name = request.data.get('file_name')
        content_type = request.data.get('content_type')
        tipo_arquivo = request.data.get('tipo', 'foto') # 'foto' ou 'video'
        
        if not file_name:
            return Response({'error': 'file_name obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)

        # Trata o nome do ficheiro e gera um identificador único
        ext = os.path.splitext(file_name)[1].lower()
        uuid_hex = uuid.uuid4().hex
        
        # Decide a pasta destino na S3 (media_private para garantir segurança)
        if tipo_arquivo == 'video':
            unique_file_key = f"media_private/videos/{uuid_hex}{ext}"
        else:
            # Assumimos que é foto por padrão
            unique_file_key = f"media_private/fotos/{uuid_hex}{ext}"

        # 🚨 AQUI ESTÁ A CORREÇÃO: Adicionamos o endpoint_url do Cloudflare
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
            endpoint_url=settings.AWS_S3_ENDPOINT_URL, 
            config=boto3.session.Config(signature_version='s3v4')
        )

        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                'Key': unique_file_key,
                'ContentType': content_type,
            },
            ExpiresIn=3600 # 1 hora para o upload
        )

        return Response({
            'presigned_url': presigned_url,
            'file_key': unique_file_key
        })

class FotoUploadView(APIView):
    """
    O React agora chama esta View APENAS depois de a foto já estar na S3.
    O nosso trabalho aqui é só gravar no Banco de Dados em milissegundos.
    """
    permission_classes = [IsAuthenticated, IsFotografoOrAdmin]

    def post(self, request, *args, **kwargs):
        destino = request.data.get('destino_upload', 'site')
        jornais_string = request.data.get('jornais')
        
        # O React agora envia o caminho onde salvou a foto na nuvem
        file_key = request.data.get('file_key') 
        album_id = request.data.get('album')
        
        if not file_key:
            return Response({'error': 'O React não informou onde guardou a foto na S3.'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Coleta metadados
        metadados = {
            'titulo': request.data.get('ftp_titulo', ''),
            'data': request.data.get('ftp_data', ''),
            'local': request.data.get('ftp_local', ''),
            'legenda': request.data.get('legenda', ''),
            'creditos': request.data.get('ftp_creditos', ''),
            'categoria': request.data.get('categoria', '')
        }
        
        jornais_ids = []
        if jornais_string:
            jornais_ids = [int(id_str.strip()) for id_str in jornais_string.split(',') if id_str.strip().isdigit()]

        try:
            # --- CENÁRIO 1: APENAS SITE ou AMBOS ---
            if destino in ['site', 'ambos']:
                
                # Vamos remover o prefixo 'media_private/' se o seu banco guarda sem ele,
                # ou manter como está dependendo da sua formatação do FileField
                path_bd = file_key.replace('media_private/', '')
                
                # Criar logo no Banco de Dados! Muito Rápido!
                foto = Foto.objects.create(
                    album_id=album_id,
                    imagem=path_bd, 
                    preco=request.data.get('preco', 0),
                    legenda=request.data.get('legenda', ''),
                    categoria=request.data.get('categoria', '')
                )
                
                # Se for "ambos", dispara o FTP usando a foto salva
                if destino == 'ambos' and jornais_ids:
                    distribuir_foto_para_ftps.delay(foto.id, jornais_ids, metadados)
                
                # Como criamos a Foto diretamente, o Django dispara os signals 
                # (ou processamento do Celery) de forma automática.
                return Response({'status': 'Gravado no Banco com Sucesso', 'foto_id': foto.id}, status=status.HTTP_201_CREATED)

            # --- CENÁRIO 2: APENAS FTP (Não salva no Banco) ---
            elif destino == 'ftp':
                if not jornais_ids:
                    return Response({'error': 'Faltam jornais para FTP.'}, status=status.HTTP_400_BAD_REQUEST)
                
                # O React mandou o ficheiro direto para o file_key. Disparar FTP:
                distribuir_foto_temporaria_ftp.delay(file_key, jornais_ids, metadados)
                return Response({'status': 'Enviado direto para o Jornal!'}, status=status.HTTP_200_OK)
                
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class VideoUploadDashboardView(APIView):
    """
    Versão Direct-to-S3 para Vídeos. Salva apenas o registo após o React confirmar o upload.
    """
    permission_classes = [IsAuthenticated, IsFotografoOrAdmin]

    def post(self, request, *args, **kwargs):
        file_key = request.data.get('file_key')
        album_id = request.data.get('album')

        if not file_key:
            return Response({'error': 'file_key obrigatorio para videos.'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            path_bd = file_key.replace('media_private/', '')
            
            video = Video.objects.create(
                album_id=album_id,
                arquivo_video=path_bd,
                titulo=request.data.get('titulo', ''),
                preco=request.data.get('preco', 0),
                categoria=request.data.get('categoria', '')
            )
            
            # O processamento pesado (criar miniatura) é delegado aos signals ou celery
            return Response({'status': 'Vídeo guardado com sucesso', 'video_id': video.id}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# =========================================================================================

class AlbumViewSet(viewsets.ModelViewSet):
    serializer_class = AlbumDashboardSerializer
    permission_classes = [IsAuthenticated, IsFotografoOrAdmin]

    def get_queryset(self):
        # 1. Pega todos os álbuns inicialmente
        queryset = Album.objects.all()

        # 🚀 2. NOVA LÓGICA: Lê o parâmetro ?is_arquivado da URL do React
        arquivado_str = self.request.query_params.get('is_arquivado')
        if arquivado_str is not None:
            if arquivado_str.lower() == 'false':
                queryset = queryset.filter(is_arquivado=False)
            elif arquivado_str.lower() == 'true':
                queryset = queryset.filter(is_arquivado=True)

        # 3. Mantém a sua regra de segurança atual (Fotógrafo só vê os dele)
        if self.request.user.papel != 'ADMIN':
            queryset = queryset.filter(fotografo=self.request.user)

        # 4. Mantém as suas anotações matemáticas perfeitas
        return queryset.annotate(
            qtd_vendida=Count(
                'fotos__itempedido',
                filter=Q(fotos__itempedido__pedido__status='PAGO')
            ),
            total_arrecadado=Coalesce(
                Sum(
                    'fotos__itempedido__preco',
                    filter=Q(fotos__itempedido__pedido__status='PAGO')
                ), 
                Value(Decimal('0.00'))
            )
        ).order_by('-id')

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

    @action(detail=True, methods=['get'])
    def baixar_original(self, request, pk=None):
        foto = self.get_object() 
        
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        
        caminho_banco = foto.imagem.name
        nome_arquivo = caminho_banco.split('/')[-1]
        
        caminho_s3 = f"media_private/{caminho_banco}".replace('//', '/')
        
        url = s3_client.generate_presigned_url(
            ClientMethod='get_object',
            Params={
                'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                'Key': caminho_s3,
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

# ==========================================
# VIEWS DE AVALIAÇÕES (GOOGLE REVIEWS)
# ==========================================

@api_view(['GET'])
@permission_classes([AllowAny])
def avaliacoes_destaques(request):
    avaliacoes = Avaliacao.objects.filter(mostrar_na_home=True).order_by('-criado_em')
    serializer = AvaliacaoSerializer(avaliacoes, many=True)
    return Response(serializer.data)

class AvaliacaoViewSet(viewsets.ModelViewSet):
    queryset = Avaliacao.objects.all().order_by('-criado_em')
    serializer_class = AvaliacaoSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

class ArquivarAlbunsEmMassaView(APIView):
    """
    Recebe uma lista de IDs do React, arquiva os álbuns e manda
    as mídias não vendidas para o Celery apagar.
    """
    permission_classes = [IsAdminUser] # 🛡️ Proteção de Segurança Máxima

    def post(self, request):
        album_ids = request.data.get('album_ids', [])
        
        if not album_ids:
            return Response({'error': 'Nenhum álbum foi selecionado.'}, status=status.HTTP_400_BAD_REQUEST)

        albuns = Album.objects.filter(id__in=album_ids)
        total_fotos_apagadas = 0
        total_videos_apagados = 0
        albuns_processados = 0

        for album in albuns:
            # 1. Filtra mídias não vendidas
            fotos_sem_venda = Foto.objects.filter(album=album).exclude(
                Q(itempedido__pedido__status='PAGO') | Q(itempedido__pedido__status='CONCLUIDO')
            ).values_list('id', flat=True)

            videos_sem_venda = Video.objects.filter(album=album).exclude(
                Q(itempedido__pedido__status='PAGO') | Q(itempedido__pedido__status='CONCLUIDO')
            ).values_list('id', flat=True)

            fotos_ids = list(fotos_sem_venda)
            videos_ids = list(videos_sem_venda)

            total_fotos_apagadas += len(fotos_ids)
            total_videos_apagados += len(videos_ids)

            # 2. Envia para o Celery
            if fotos_ids or videos_ids:
                apagar_midias_antigas_task.delay(fotos_ids, videos_ids)

            # 3. Arquiva o Álbum
            album.is_arquivado = True
            album.save()
            albuns_processados += 1

        return Response({
            'message': f'Sucesso! {albuns_processados} álbuns arquivados.',
            'fotos_apagadas': total_fotos_apagadas,
            'videos_apagados': total_videos_apagados
        }, status=status.HTTP_200_OK)
