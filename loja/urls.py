# loja/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CarrinhoView, 
    CheckoutView, 
    StripeWebhookView, 
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
    path('checkout/', CheckoutView.as_view(), name='checkout'),
    path('webhooks/stripe/', StripeWebhookView.as_view(), name='stripe-webhook'),
    path('minhas-compras/', MinhasComprasView.as_view(), name='minhas-compras'),
    path('download-foto/<int:foto_id>/', DownloadFotoView.as_view(), name='download-foto'),
    path('carrinho/aplicar-cupom/', AplicarCupomView.as_view(), name='aplicar-cupom'),
    path('dashboard/vendas/', VendasFotografoView.as_view(), name='dashboard-vendas'),
    path('admin/stats/', AdminStatsView.as_view(), name='admin-stats'),
]

# --- Adiciona as URLs geradas pelo roteador à nossa lista ---
urlpatterns += router.urls