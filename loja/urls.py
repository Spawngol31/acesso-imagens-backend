# loja/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CarrinhoView, 
    MercadoPagoCheckoutView, 
    MercadoPagoWebhookView, 
    MinhasComprasView, 
    DownloadFotoView, 
    VendasFotografoView, 
    CupomViewSet,
    AplicarCupomView, 
    AdminStatsView
)

# --- Cria um roteador para as ViewSets do dashboard deste app ---
router = DefaultRouter()
router.register(r'dashboard/cupons', CupomViewSet, basename='dashboard-cupom')

# --- URLs manuais (as que já tínhamos) ---
urlpatterns = [
    # URLs do Cliente
    path('carrinho/', CarrinhoView.as_view(), name='carrinho'),
    path('carrinho/aplicar-cupom/', AplicarCupomView.as_view(), name='aplicar-cupom'),

    path('checkout/mp/', MercadoPagoCheckoutView.as_view(), name='mp-checkout'),
    path('webhooks/mp/', MercadoPagoWebhookView.as_view(), name='mp-webhook'),

    path('minhas-compras/', MinhasComprasView.as_view(), name='minhas-compras'),
    path('download-foto/<int:foto_id>/', DownloadFotoView.as_view(), name='download-foto'),
    
    path('dashboard/vendas/', VendasFotografoView.as_view(), name='dashboard-vendas'),
    path('admin/stats/', AdminStatsView.as_view(), name='admin-stats'),
]

# --- Adiciona as URLs geradas pelo roteador à nossa lista ---
urlpatterns += router.urls