from django.shortcuts import render

# galeria/views.py
import boto3
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from .permissions import IsFotografo
from .serializers import FotoUploadSerializer
from rest_framework import generics
from rest_framework.permissions import AllowAny
from .models import Album, Foto, Video
from .models import FaceIndexada
from .serializers import (
    AlbumDashboardSerializer, FotoDashboardSerializer, 
    VideoDashboardSerializer, VideoUploadSerializer
)
from .serializers import AlbumSerializer, AlbumDetailSerializer, FotoSerializer

class FotoUploadView(APIView):
    # Parsers para lidar com upload de arquivos
    parser_classes = [MultiPartParser, FormParser]
    # Garante que o usuário está logado E é um fotógrafo
    permission_classes = [IsAuthenticated, IsFotografo]

    def post(self, request, format=None):
        serializer = FotoUploadSerializer(data=request.data)
        if serializer.is_valid():
            # Antes de salvar, vamos garantir que o fotógrafo só pode adicionar
            # fotos em seus próprios álbuns.
            album = serializer.validated_data['album']
            if album.fotografo != request.user:
                return Response(
                    {'error': 'Você não tem permissão para adicionar fotos a este álbum.'},
                    status=status.HTTP_403_FORBIDDEN
                )

            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class FotoViewSet(viewsets.ModelViewSet):
    """
    API endpoint que permite aos fotógrafos ver, editar e deletar
    suas próprias fotos.
    """
    serializer_class = FotoDashboardSerializer
    permission_classes = [IsAuthenticated, IsFotografo]
    
    # Limitamos as ações. A criação (POST) ainda é feita pelo endpoint de upload.
    http_method_names = ['get', 'put', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        """
        ESSENCIAL: Garante que a ViewSet retorne apenas as fotos
        que pertencem a álbuns do fotógrafo logado.
        """
        return Foto.objects.filter(album__fotografo=self.request.user).order_by('-data_upload')

class VideoUploadView(APIView):
    """
    Endpoint para o fotógrafo fazer o upload de um novo vídeo e sua miniatura.
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated, IsFotografo]

    def post(self, request, format=None):
        serializer = VideoUploadSerializer(data=request.data)
        if serializer.is_valid():
            album = serializer.validated_data['album']
            if album.fotografo != request.user:
                return Response(
                    {'error': 'Você não tem permissão para adicionar vídeos a este álbum.'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VideoViewSet(viewsets.ModelViewSet):
    """
    API endpoint que permite aos fotógrafos ver, editar e deletar
    seus próprios vídeos.
    """
    serializer_class = VideoDashboardSerializer
    permission_classes = [IsAuthenticated, IsFotografo]
    http_method_names = ['get', 'put', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        """
        Garante que a ViewSet retorne apenas os vídeos
        que pertencem a álbuns do fotógrafo logado.
        """
        return Video.objects.filter(album__fotografo=self.request.user).order_by('-data_upload')

class AlbumListView(generics.ListAPIView):
    """
    View para listar todos os álbuns.
    Qualquer pessoa pode ver a lista de álbuns.
    """
    queryset = Album.objects.all().order_by('-criado_em')
    serializer_class = AlbumSerializer
    permission_classes = [AllowAny] # Permite acesso não autenticado

class AlbumDetailView(generics.RetrieveAPIView):
    """
    View para ver os detalhes de um único álbum, incluindo todas as suas fotos.
    """
    queryset = Album.objects.all()
    serializer_class = AlbumDetailSerializer
    permission_classes = [AllowAny]

class AlbumViewSet(viewsets.ModelViewSet):
    """
    API endpoint que permite aos fotógrafos criar, ver, editar e deletar
    seus próprios álbuns.
    """
    serializer_class = AlbumDashboardSerializer
    # Garante que apenas fotógrafos autenticados acessem
    permission_classes = [IsAuthenticated, IsFotografo]

    def get_queryset(self):
        """
        ESSENCIAL: Esta função sobrescreve o comportamento padrão para garantir
        que a ViewSet retorne apenas os álbuns pertencentes ao fotógrafo logado.
        """
        return Album.objects.filter(fotografo=self.request.user).order_by('-data_evento')

    def perform_create(self, serializer):
        """
        ESSENCIAL: Esta função é chamada ao criar um novo álbum (POST).
        Ela associa automaticamente o novo álbum ao fotógrafo logado.
        """
        serializer.save(fotografo=self.request.user)

class BuscaFacialView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, format=None):
        if 'imagem_referencia' not in request.FILES:
            return Response({"error": "Nenhum arquivo de imagem fornecido."}, status=status.HTTP_400_BAD_REQUEST)

        imagem_referencia = request.FILES['imagem_referencia'].read()

        try:
            rekognition_client = boto3.client('rekognition', region_name=settings.AWS_REKOGNITION_REGION_NAME)

            response = rekognition_client.search_faces_by_image(
                CollectionId=settings.AWS_REKOGNITION_COLLECTION_ID,
                Image={'Bytes': imagem_referencia},
                FaceMatchThreshold=95, # Limiar de confiança (ajuste conforme necessário)
                MaxFaces=5
            )

            face_ids_encontrados = [match['Face']['FaceId'] for match in response.get('FaceMatches', [])]
            if not face_ids_encontrados:
                return Response([], status=status.HTTP_200_OK) # Retorna lista vazia se não encontrar

            # Busca no nosso banco de dados quais fotos contêm essas faces
            faces_no_db = FaceIndexada.objects.filter(rekognition_face_id__in=face_ids_encontrados)

            # Obtém os IDs das fotos, sem duplicatas
            foto_ids = faces_no_db.values_list('foto_id', flat=True).distinct()

            fotos_encontradas = Foto.objects.filter(id__in=foto_ids)

            # Serializa os resultados para enviar ao cliente
            # Reutilizamos o FotoSerializer que já exibe a miniatura com marca d'água
            serializer = FotoSerializer(fotos_encontradas, many=True, context={'request': request})
            return Response(serializer.data)

        except Exception as e:
            print(f"ERRO NA BUSCA FACIAL: {e}")
            return Response({"error": "Ocorreu um erro ao processar a busca facial."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
