# galeria/views.py

import boto3
from django.conf import settings
from rest_framework import generics, viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action
from decimal import Decimal, InvalidOperation

# Importa os modelos
from .models import Album, Foto, Video, FaceIndexada

# Importa os serializers
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

# --- CORREÇÃO DA IMPORTAÇÃO ---
# As permissões agora vêm do app 'contas'
from contas.permissions import IsFotografoOrAdmin, IsAdminUser
from contas.models import Usuario


# --- VIEWS PÚBLICAS (PARA OS CLIENTES) ---

class AlbumListView(generics.ListAPIView):
    queryset = Album.objects.filter(is_publico=True, is_arquivado=False).order_by('-data_evento')
    serializer_class = AlbumSerializer
    permission_classes = [AllowAny]

class AlbumDetailView(generics.RetrieveAPIView):
    queryset = Album.objects.filter(is_publico=True, is_arquivado=False)
    serializer_class = AlbumDetailSerializer
    permission_classes = [AllowAny]
    lookup_field = 'id'

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response

class BuscaFacialView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        imagem_referencia = request.FILES.get('imagem_referencia')
        if not imagem_referencia:
            return Response({"error": "Nenhuma imagem de referência enviada."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            rekognition_client = boto3.client('rekognition', region_name=settings.AWS_REKOGNITION_REGION_NAME)
            response = rekognition_client.search_faces_by_image(
                CollectionId=settings.AWS_REKOGNITION_COLLECTION_ID,
                Image={'Bytes': imagem_referencia.read()},
                MaxFaces=5,
                FaceMatchThreshold=95
            )
            
            face_matches = response.get('FaceMatches', [])
            if not face_matches:
                return Response([], status=status.HTTP_200_OK)

            matched_face_ids = [match['Face']['FaceId'] for match in face_matches]
            
            fotos_encontradas_ids = FaceIndexada.objects.filter(
                rekognition_face_id__in=matched_face_ids
            ).values_list('foto_id', flat=True).distinct()
            
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


# --- VIEWS DO PAINEL DO FOTÓGRAFO (DASHBOARD) ---

class FotoUploadView(generics.CreateAPIView):
    queryset = Foto.objects.all()
    serializer_class = FotoUploadSerializer
    permission_classes = [IsAuthenticated, IsFotografoOrAdmin] # Correção: Usa IsFotografoOrAdmin

class VideoUploadDashboardView(generics.CreateAPIView):
    queryset = Video.objects.all()
    serializer_class = VideoUploadSerializer
    permission_classes = [IsAuthenticated, IsFotografoOrAdmin] # Correção: Usa IsFotografoOrAdmin

class AlbumViewSet(viewsets.ModelViewSet):
    serializer_class = AlbumDashboardSerializer
    permission_classes = [IsAuthenticated, IsFotografoOrAdmin] # Correção: Usa IsFotografoOrAdmin

    def get_queryset(self):
        # Admin vê todos os álbuns, Fotógrafo vê apenas os seus
        if self.request.user.papel == 'ADMIN':
            return Album.objects.all()
        return Album.objects.filter(fotografo=self.request.user)

    def perform_create(self, serializer):
        # --- LÓGICA DE CRIAÇÃO CORRIGIDA ---
        # Se for um fotógrafo a criar, associa-o automaticamente
        if self.request.user.papel == Usuario.Papel.FOTOGRAFO:
            serializer.save(fotografo=self.request.user)
        
        # Se for um Admin, ele DEVE enviar o 'fotografo_id' no pedido.
        # Se ele não enviar, o 'fotografo' vem no serializer.save()
        # e o modelo irá levantar um erro de 'NOT NULL', o que é correto.
        # O frontend do Admin (se for construir) deve permitir selecionar um fotógrafo.
        elif self.request.user.papel == Usuario.Papel.ADMIN:
            # A lógica de associar ao 'fotografo' enviado já é tratada pelo serializer.
            # Se o 'fotografo' não for enviado, o serializer.save() irá falhar
            # (o que é o comportamento de segurança esperado).
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

        if new_price_str is None:
            return Response({'error': 'Preço não fornecido.'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            new_price = Decimal(new_price_str)
            if new_price < 0:
                raise InvalidOperation
        except InvalidOperation:
             return Response({'error': 'Preço inválido.'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Esta é a "magia": atualiza todas as fotos do álbum de uma vez
        count = album.fotos.all().update(preco=new_price)
        return Response({'status': f'{count} fotos atualizadas com sucesso para R$ {new_price:.2f}'})

    @action(detail=True, methods=['post'])
    def bulk_update_videos(self, request, pk=None):
        album = self.get_object()
        new_price_str = request.data.get('preco')
        
        if new_price_str is None:
            return Response({'error': 'Preço não fornecido.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            new_price = Decimal(new_price_str)
            if new_price < 0:
                raise InvalidOperation
        except InvalidOperation:
             return Response({'error': 'Preço inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        # Atualiza todos os vídeos do álbum de uma vez
        count = album.videos.all().update(preco=new_price)
        return Response({'status': f'{count} vídeos atualizados com sucesso para R$ {new_price:.2f}'})

class FotoViewSet(viewsets.ModelViewSet):
    serializer_class = FotoDashboardSerializer
    permission_classes = [IsAuthenticated, IsFotografoOrAdmin] # Correção: Usa IsFotografoOrAdmin

    def get_queryset(self):
        if self.request.user.papel == 'ADMIN':
            return Foto.objects.all()
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

class VideoViewSet(viewsets.ModelViewSet):
    serializer_class = VideoDashboardSerializer
    permission_classes = [IsAuthenticated, IsFotografoOrAdmin] # Correção: Usa IsFotografoOrAdmin

    def get_queryset(self):
        if self.request.user.papel == 'ADMIN':
            return Video.objects.all()
        return Video.objects.filter(album__fotografo=self.request.user)