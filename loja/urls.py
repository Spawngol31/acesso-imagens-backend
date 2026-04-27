# loja/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CarrinhoView, 
    MercadoPagoCheckoutView,
    MercadoPagoProcessPaymentView, 
    MercadoPagoWebhookView, 
    MinhasComprasView, 
    DownloadFotoView,
    EnviarFotoEmailView,
    VendasFotografoView, 
    CupomViewSet,
    ExportarPagamentosCSVView,
    AplicarCupomView, 
    AdminStatsView,
    AdminVendasJSONView,
    RegistrarPagamentoFotografoView,
    AdminHistoricoPagamentosView,
    FotografoVendasJSONView, 
    FotografoHistoricoPagamentosView
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
    path('checkout/mp/process/', MercadoPagoProcessPaymentView.as_view(), name='mp-process'), # <--- ADICIONE ESTA LINHA
    path('webhooks/mp/', MercadoPagoWebhookView.as_view(), name='mp-webhook'),

    path('minhas-compras/', MinhasComprasView.as_view(), name='minhas-compras'),
    path('download-foto/<int:foto_id>/', DownloadFotoView.as_view(), name='download-foto'),
    path('download-foto/<int:foto_id>/enviar-email/', EnviarFotoEmailView.as_view(), name='enviar_foto_email'),

    path('dashboard/minhas-vendas-json/', FotografoVendasJSONView.as_view(), name='fotografo-vendas-json'),
    path('dashboard/meus-recibos/', FotografoHistoricoPagamentosView.as_view(), name='fotografo-recibos'),
    path('dashboard/vendas/', VendasFotografoView.as_view(), name='dashboard-vendas'),
    path('admin/stats/', AdminStatsView.as_view(), name='admin-stats'),
    path('admin/exportar-pagamentos/', ExportarPagamentosCSVView.as_view(), name='exportar-pagamentos'),
    path('admin/vendas-json/', AdminVendasJSONView.as_view(), name='admin-vendas-json'),
    path('admin/registrar-pagamento-fotografo/', RegistrarPagamentoFotografoView.as_view(), name='registrar-pagamento'),
    path('admin/historico-pagamentos/', AdminHistoricoPagamentosView.as_view(), name='historico-pagamentos'),
]

# --- Adiciona as URLs geradas pelo roteador à nossa lista ---
urlpatterns += router.urls