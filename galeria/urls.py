# galeria/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AlbumListView, 
    AlbumDetailView, 
    BuscaFacialView,
    FotoUploadView,
    VideoUploadDashboardView,  # <-- Nome corrigido
    AlbumViewSet,
    FotoViewSet,
    VideoViewSet
)

# Roteador para os endpoints do painel (Dashboard)
dashboard_router = DefaultRouter()
dashboard_router.register(r'albuns', AlbumViewSet, basename='dashboard-album')
dashboard_router.register(r'fotos', FotoViewSet, basename='dashboard-foto')
dashboard_router.register(r'videos', VideoViewSet, basename='dashboard-video')

urlpatterns = [
    # URLs Públicas (para clientes)
    path('albuns/', AlbumListView.as_view(), name='album-list'),
    path('albuns/<int:id>/', AlbumDetailView.as_view(), name='album-detail'),
    path('fotos/busca-facial/', BuscaFacialView.as_view(), name='busca-facial'),
    
    # URLs do Painel (para fotógrafos/admins)
    path('fotos/upload/', FotoUploadView.as_view(), name='foto-upload'),
    path('dashboard/videos/upload/', VideoUploadDashboardView.as_view(), name='video-upload'), # <-- Nome corrigido
    path('dashboard/', include(dashboard_router.urls)),
]