# galeria/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AlbumListView, 
    AlbumDetailView, 
    BuscaFacialView,
    FotoUploadView,
    VideoUploadDashboardView,
    AlbumViewSet,
    FotoViewSet,
    VideoViewSet,
    album_share_preview,
    StatusFilaProcessamentoView,
    AvaliacaoViewSet,
    avaliacoes_destaques
)

# Roteador para os endpoints do painel (Dashboard)
dashboard_router = DefaultRouter()
dashboard_router.register(r'albuns', AlbumViewSet, basename='dashboard-album')
dashboard_router.register(r'fotos', FotoViewSet, basename='dashboard-foto')
dashboard_router.register(r'videos', VideoViewSet, basename='dashboard-video')
# --- REGISTRO DA ROTA DO ADMIN PARA AVALIAÇÕES ---
dashboard_router.register(r'avaliacoes', AvaliacaoViewSet, basename='dashboard-avaliacao')

urlpatterns = [
    # URLs Públicas (para clientes)
    path('albuns/', AlbumListView.as_view(), name='album-list'),
    path('albuns/<int:id>/', AlbumDetailView.as_view(), name='album-detail'),
    path('fotos/busca-facial/', BuscaFacialView.as_view(), name='busca-facial'),
    
    # --- ROTA PÚBLICA DAS AVALIAÇÕES DA HOME PAGE ---
    path('avaliacoes/destaques/', avaliacoes_destaques, name='avaliacoes-destaques'),
    
    # ROTA DE COMPARTILHAMENTO
    path('share/album/<int:pk>/', album_share_preview, name='album-share'),
    
    # URLs do Painel (para fotógrafos/admins)
    path('fotos/upload/', FotoUploadView.as_view(), name='foto-upload'),
    path('dashboard/videos/upload/', VideoUploadDashboardView.as_view(), name='video-upload'),
    path('dashboard/status-fila/', StatusFilaProcessamentoView.as_view(), name='status-fila'),
    
    path('dashboard/', include(dashboard_router.urls)),
]