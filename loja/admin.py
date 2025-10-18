# loja/admin.py
from django.contrib import admin
from .models import Pedido, ItemPedido, FotoComprada, Cupom

# Esta classe permite-nos ver os itens de um pedido diretamente na página do pedido
class ItemPedidoInline(admin.TabularInline):
    model = ItemPedido
    extra = 0 # Não mostra formulários extra vazios
    readonly_fields = ('foto', 'preco') # Torna os campos apenas de leitura
    can_delete = False # Impede que se apaguem itens de um pedido já feito

    def has_add_permission(self, request, obj=None):
        return False # Impede que se adicionem novos itens a um pedido já feito

@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ('id', 'cliente', 'status', 'valor_total', 'criado_em')
    list_filter = ('status', 'criado_em', 'cliente')
    search_fields = ('cliente__email', 'stripe_payment_intent_id')
    inlines = [ItemPedidoInline] # Adiciona a visualização dos itens dentro do pedido

@admin.register(ItemPedido)
class ItemPedidoAdmin(admin.ModelAdmin):
    list_display = ('pedido', 'foto', 'preco')

@admin.register(FotoComprada)
class FotoCompradaAdmin(admin.ModelAdmin):
    list_display = ('cliente', 'foto', 'data_compra', 'data_expiracao')
    list_filter = ('cliente',)
    search_fields = ('cliente__email', 'foto__legenda')

@admin.register(Cupom)
class CupomAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'fotografo', 'desconto_percentual', 'ativo', 'data_validade')
    list_filter = ('ativo', 'fotografo')
    search_fields = ('codigo',)