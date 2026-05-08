# loja/admin.py

import csv
from django.http import HttpResponse
from django.contrib import admin, messages
from django.db.models import Sum
from .models import Pedido, ItemPedido, FotoComprada, Cupom
from django.utils import timezone
from rangefilter.filters import DateRangeFilter # <-- IMPORT NOVO PARA O CALENDÁRIO

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

# --- 2. AÇÃO MÁGICA ATUALIZADA: EXPORTAR PARA EXCEL (CSV) ---
@admin.action(description='Imprimir Relatório de Pagamento (Excel)')
def exportar_pagamento_csv(modeladmin, request, queryset):
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig') 
    response['Content-Disposition'] = 'attachment; filename="relatorio_pagamento_fotografos.csv"'
    
    writer = csv.writer(response, delimiter=';')
    writer.writerow(['ID Pedido', 'Data da Venda', 'Status', 'Fotógrafo', 'ID da Foto', 'Valor da Venda (R$)', 'Comissão a Pagar (R$)'])
    
    total_geral_comissao = 0.0 
    
    for item in queryset:
        try:
            nome_fotografo = item.foto.album.fotografo.nome_completo or item.foto.album.fotografo.email
        except AttributeError:
            nome_fotografo = "Desconhecido"

        # 🪄 USAMOS A MATEMÁTICA PROPORCIONAL PARA O EXCEL TAMBÉM
        valor_venda_real = modeladmin.get_valor_real_item(item)
        comissao = valor_venda_real * 0.95 
        
        total_geral_comissao += comissao 

        data_local = timezone.localtime(item.pedido.criado_em)

        writer.writerow([
            item.pedido.id,
            data_local.strftime("%d/%m/%Y %H:%M"),
            item.pedido.status,
            nome_fotografo,
            item.foto.id,
            str(f"{valor_venda_real:.2f}").replace('.', ','),
            str(f"{comissao:.2f}").replace('.', ',')
        ])
        
    writer.writerow([]) 
    writer.writerow(['', '', '', '', '', 'TOTAL A PAGAR:', str(f"{total_geral_comissao:.2f}").replace('.', ',')])
        
    return response

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
    raw_id_fields = ('cliente',)
    list_filter = ('status', ('criado_em', DateRangeFilter), 'cliente') # Adicionado calendário aqui também
    search_fields = ('cliente__email', 'id_pagamento_externo')
    inlines = [ItemPedidoInline]

    def get_metodo_pagamento(self, obj):
        return getattr(obj, 'metodo_pagamento', 'Não informado')
    get_metodo_pagamento.short_description = 'Forma de Pgto'


# --- PAINEL FINANCEIRO DOS FOTÓGRAFOS ---
@admin.register(ItemPedido)
class ItemPedidoAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'get_fotografo', 'foto', 'get_data_venda', 
        'get_metodo_pagamento', 'get_status_pedido', 'valor_venda', 'valor_fotografo'
    )
    raw_id_fields = ('pedido', 'foto')
    list_filter = (('pedido__criado_em', DateRangeFilter), FotografoFilter, 'pedido__status')
    search_fields = ('foto__album__fotografo__email', 'pedido__id')
    actions = [exportar_pagamento_csv]

    # 🚀 1. OTIMIZAÇÕES EXTRAS DE VELOCIDADE
    list_per_page = 30 
    show_full_result_count = False 

    # 🚀 2. A MÁGICA: SÓ CARREGA SE TIVER FILTRO
    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related(
            'foto', 'foto__album', 'foto__album__fotografo', 'pedido'
        ).prefetch_related('pedido__itens')
        
        # 🚀 CORRIGIDO: Adicionados os nomes corretos que o DateRangeFilter usa
        tem_filtro = any(chave in request.GET for chave in (
            'q', 'fotografo_id', 'pedido__status', 
            'pedido__criado_em__range__gte', 'pedido__criado_em__range__lte'
        ))
        
        if not tem_filtro:
            return qs.none() 
            
        return qs

    # 🚀 3. O RESUMO MATEMÁTICO INTELIGENTE (AGORA É ÚNICO!)
    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        
        if hasattr(response, 'context_data') and 'cl' in response.context_data:
            
            # 🚀 CORRIGIDO AQUI TAMBÉM:
            tem_filtro = any(chave in request.GET for chave in (
                'q', 'fotografo_id', 'pedido__status', 
                'pedido__criado_em__range__gte', 'pedido__criado_em__range__lte'
            ))
            
            if not tem_filtro:
                messages.info(request, "⚡ MODO RÁPIDO: A tela começa vazia para não sobrecarregar o servidor. Use os filtros ao lado (Fotógrafo, Data) para carregar as vendas.")
            else:
                queryset_filtrado = response.context_data['cl'].queryset
                
                if queryset_filtrado.count() < 1000:
                    total_real_vendas = sum(self.get_valor_real_item(item) for item in queryset_filtrado)
                    total_pagar = total_real_vendas * 0.95
                    
                    if total_real_vendas > 0:
                        messages.success(request, f"💰 RESUMO DO FILTRO: Vendas Líquidas (R$ {total_real_vendas:.2f}) | TOTAL A PAGAR: R$ {total_pagar:.2f}")
                else:
                    messages.warning(request, "⚠️ O filtro tem muitos itens! A matemática de tela foi desligada. Imprima o Relatório Excel para ver os totais.")
                    
        return response

    # --- 🧮 CORAÇÃO DA MATEMÁTICA PROPORCIONAL ---
    def get_valor_real_item(self, obj):
        if not obj.preco or not obj.pedido.valor_total:
            return 0.0
        
        subtotal_cheio = sum(item.preco for item in obj.pedido.itens.all())
        
        if subtotal_cheio > 0:
            fator_desconto = float(obj.pedido.valor_total) / float(subtotal_cheio)
            return float(obj.preco) * fator_desconto
        
        return float(obj.preco)

    # --- CAMPOS DA TELA ---
    def valor_venda(self, obj):
        valor_real = self.get_valor_real_item(obj)
        return f"R$ {valor_real:.2f}"
    valor_venda.short_description = 'Valor Pago (c/ Desconto)'

    def valor_fotografo(self, obj):
        valor_real = self.get_valor_real_item(obj)
        valor_receber = valor_real * 0.95
        return f"R$ {valor_receber:.2f}"
    valor_fotografo.short_description = 'Comissão (Un.)'

    # --- FUNÇÕES DE EXIBIÇÃO AUXILIARES ---
    def get_fotografo(self, obj):
        try:
            return obj.foto.album.fotografo.nome_completo
        except AttributeError:
            return "Sem fotógrafo"
    get_fotografo.short_description = 'Fotógrafo'

    def get_data_venda(self, obj):
        data_local = timezone.localtime(obj.pedido.criado_em)
        return data_local.strftime("%d/%m/%Y %H:%M")
    get_data_venda.short_description = 'Data'

    def get_status_pedido(self, obj):
        return obj.pedido.status
    get_status_pedido.short_description = 'Status'

    def get_metodo_pagamento(self, obj):
        return getattr(obj.pedido, 'metodo_pagamento', 'Não informado')
    get_metodo_pagamento.short_description = 'Forma de Pgto'


@admin.register(FotoComprada)
class FotoCompradaAdmin(admin.ModelAdmin):
    list_display = ('cliente', 'foto', 'data_compra')
    
    # 🛡️ MÁGICA ATUALIZADA: Usamos apenas 'foto' e 'cliente' 
    # (que são as chaves estrangeiras que você realmente tem no modelo)
    raw_id_fields = ('foto', 'cliente') 
    
    # OPCIONAL: Protege os campos financeiros reais para não serem alterados por engano
    # readonly_fields = ('foto', 'cliente')

@admin.register(Cupom)
class CupomAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'fotografo', 'desconto_percentual', 'ativo', 'data_validade')
    list_filter = ('ativo', 'fotografo')
    search_fields = ('codigo',)