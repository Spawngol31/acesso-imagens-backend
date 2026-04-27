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

# --- 2. AÇÃO MÁGICA: EXPORTAR PARA EXCEL (CSV) ---
@admin.action(description='Imprimir Relatório de Pagamento (Excel)')
def exportar_pagamento_csv(modeladmin, request, queryset):
    # Configura o ficheiro para baixar com a codificação correta para acentos no Excel
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig') 
    response['Content-Disposition'] = 'attachment; filename="relatorio_pagamento_fotografos.csv"'
    
    writer = csv.writer(response, delimiter=';')
    
    # Cabeçalho da Planilha
    writer.writerow(['ID Pedido', 'Data da Venda', 'Status', 'Fotógrafo', 'ID da Foto', 'Valor da Venda (R$)', 'Comissão a Pagar (R$)'])
    
    total_geral_comissao = 0.0 # <--- Nossa nova variável para guardar o total!
    
    for item in queryset:
        # Pega o fotógrafo respeitando o caminho do seu modelo (Foto -> Album -> Fotógrafo)
        try:
            nome_fotografo = item.foto.album.fotografo.nome_completo or item.foto.album.fotografo.email
        except AttributeError:
            nome_fotografo = "Desconhecido"

        valor_venda = float(item.preco) if item.preco else 0.0
        comissao = valor_venda * 0.95 # A sua taxa de 95% para o fotógrafo
        
        total_geral_comissao += comissao # <--- Vai somando o valor de cada linha

        data_local = timezone.localtime(item.pedido.criado_em)

        writer.writerow([
            item.pedido.id,
            data_local.strftime("%d/%m/%Y %H:%M"),
            item.pedido.status,
            nome_fotografo,
            item.foto.id,
            str(f"{valor_venda:.2f}").replace('.', ','),
            str(f"{comissao:.2f}").replace('.', ',')
        ])
        
    # --- ADICIONANDO A LINHA DE TOTAL NO FINAL DA PLANILHA ---
    writer.writerow([]) # Uma linha em branco para separar e ficar bonito
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
        'id', 
        'get_fotografo', 
        'foto', 
        'get_data_venda', 
        'get_metodo_pagamento',
        'get_status_pedido', 
        'valor_venda', 
        'valor_fotografo'
    )
    
    # 3. COLOCAMOS O NOVO FILTRO DE CALENDÁRIO AQUI!
    list_filter = (
        ('pedido__criado_em', DateRangeFilter), # <--- Calendário De / Até
        FotografoFilter, 
        'pedido__status',         
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Diz ao Django para "pre-joinar" estas 3 tabelas de uma vez só!
        return qs.select_related('foto', 'foto__album', 'foto__album__fotografo', 'pedido')

    search_fields = ('foto__album__fotografo__email', 'pedido__id')

    # Adicionando o botão de exportar na tela
    actions = [exportar_pagamento_csv]

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
        except AttributeError:
            return "Sem fotógrafo"
    get_fotografo.short_description = 'Fotógrafo'

    def get_data_venda(self, obj):
        # A mágica acontece aqui: pegamos a hora de Londres e convertemos para São Paulo
        data_local = timezone.localtime(obj.pedido.criado_em)
        return data_local.strftime("%d/%m/%Y %H:%M")
    get_data_venda.short_description = 'Data'

    def get_status_pedido(self, obj):
        # Vai no pedido principal e pega o status dele (ex: PAGO, PENDENTE)
        return obj.pedido.status
    get_status_pedido.short_description = 'Status'

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