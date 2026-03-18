# loja/admin.py

from django.contrib import admin, messages
from django.db.models import Sum
from .models import Pedido, ItemPedido, FotoComprada, Cupom

# --- 1. CRIAMOS O FILTRO FORÇADO DE FOTÓGRAFOS ---
class FotografoFilter(admin.SimpleListFilter):
    title = 'fotógrafo' # O nome que vai aparecer na caixinha lateral
    parameter_name = 'fotografo_id'

    def lookups(self, request, model_admin):
        # Vai no banco de dados e busca o ID e o Email de quem já fez vendas
        fotografos = model_admin.model.objects.filter(
            foto__album__fotografo__isnull=False
        ).values_list(
            'foto__album__fotografo__id', 
            'foto__album__fotografo__email'
        ).distinct()
        return fotografos

    def queryset(self, request, queryset):
        # Aplica o filtro quando você clica no nome de alguém
        if self.value():
            return queryset.filter(foto__album__fotografo__id=self.value())
        return queryset

# --------------------------------------------------

class ItemPedidoInline(admin.TabularInline):
    model = ItemPedido
    extra = 0
    readonly_fields = ('foto', 'preco')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ('id', 'cliente', 'status', 'get_metodo_pagamento', 'valor_total', 'criado_em')
    list_filter = ('status', 'criado_em', 'cliente')
    search_fields = ('cliente__email', 'id_pagamento_externo')
    inlines = [ItemPedidoInline]

    def get_metodo_pagamento(self, obj):
        return getattr(obj, 'metodo_pagamento', 'Não informado')
    get_metodo_pagamento.short_description = 'Forma de Pgto'


# --- PAINEL FINANCEIRO DOS FOTÓGRAFOS ---
@admin.register(ItemPedido)
class ItemPedidoAdmin(admin.ModelAdmin):
    list_display = (
        'id', 
        'get_fotografo', 
        'foto', 
        'get_data_venda', 
        'get_metodo_pagamento', 
        'valor_venda', 
        'valor_fotografo'
    )
    
    # 2. COLOCAMOS O NOVO FILTRO AQUI!
    list_filter = (
        'pedido__criado_em',      
        FotografoFilter, # <--- A mágica acontece aqui agora
        'pedido__status',         
    )
    
    search_fields = ('foto__album__fotografo__email', 'pedido__id')

    # A MÁGICA DA SOMA AUTOMÁTICA NO TOPO DA TELA
    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        
        if hasattr(response, 'context_data') and 'cl' in response.context_data:
            queryset_filtrado = response.context_data['cl'].queryset
            
            total_vendas = queryset_filtrado.aggregate(total=Sum('preco'))['total'] or 0
            
            TAXA_FOTOGRAFO = 0.95 
            total_pagar = float(total_vendas) * TAXA_FOTOGRAFO
            
            if total_vendas > 0:
                mensagem = f"💰 RESUMO DA TELA ATUAL: Vendas Totais (R$ {total_vendas:.2f}) | TOTAL LÍQUIDO A PAGAR AOS FOTÓGRAFOS: R$ {total_pagar:.2f}"
                messages.success(request, mensagem)
                
        return response

    def get_fotografo(self, obj):
        try:
            return obj.foto.album.fotografo.nome_completo
        except Exception:
            return "Sem fotógrafo"
    get_fotografo.short_description = 'Fotógrafo'

    def get_data_venda(self, obj):
        return obj.pedido.criado_em.strftime("%d/%m/%Y %H:%M")
    get_data_venda.short_description = 'Data'

    def get_metodo_pagamento(self, obj):
        return getattr(obj.pedido, 'metodo_pagamento', 'Não informado')
    get_metodo_pagamento.short_description = 'Forma de Pgto'

    def valor_venda(self, obj):
        return f"R$ {obj.preco:.2f}"
    valor_venda.short_description = 'Valor de Venda'

    def valor_fotografo(self, obj):
        if not obj.preco:
            return "R$ 0.00"
            
        TAXA_FOTOGRAFO = 0.95 
        valor_receber = float(obj.preco) * TAXA_FOTOGRAFO
        return f"R$ {valor_receber:.2f}"
    valor_fotografo.short_description = 'Comissão (Un.)'


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