from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BuscaFacialView
from .views import (
    FotoUploadView, AlbumListView, AlbumDetailView, 
    AlbumViewSet, FotoViewSet, VideoUploadView, VideoViewSet
)

urlpatterns = [
    # URL de upload para fotógrafos
    path('fotos/upload/', FotoUploadView.as_view(), name='foto_upload'),
    # URL para listar todos os álbuns
    path('albuns/', AlbumListView.as_view(), name='album-list'),

    # URL para ver um álbum específico. <int:pk> captura o ID do álbum.
    path('albuns/<int:pk>/', AlbumDetailView.as_view(), name='album-detail'),
]

# Cria um roteador
router = DefaultRouter()
# Registra nossa ViewSet. O router irá criar as URLs para nós.
# O prefixo será 'dashboard/albuns'
router.register(r'dashboard/albuns', AlbumViewSet, basename='dashboard-album')
# Registra a nova ViewSet de Fotos
router.register(r'dashboard/fotos', FotoViewSet, basename='dashboard-foto')
router.register(r'dashboard/videos', VideoViewSet, basename='dashboard-video')

# As URLs de upload são manuais pois não fazem parte de um ViewSet padrão.
urlpatterns += [
    path('dashboard/videos/upload/', VideoUploadView.as_view(), name='video-upload'),
    path('fotos/busca-facial/', BuscaFacialView.as_view(), name='busca-facial'),
]
# Adiciona as URLs geradas pelo roteador às nossas URLs existentes
urlpatterns += router.urls
