# loja/serializers.py

from decimal import Decimal
from rest_framework import serializers
from .models import Carrinho, ItemCarrinho, Pedido, ItemPedido, Cupom
from galeria.models import Foto
# Não precisamos mais de importar o FotoSerializer da galeria

# --- SERIALIZER DE CUPOM (CORRETO) ---
class CupomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cupom
        fields = ['id', 'codigo', 'desconto_percentual', 'ativo', 'data_validade']

# --- NOVO SERIALIZER "LEVE" PARA FOTOS (OTIMIZADO) ---
# Este serializer é usado apenas para o carrinho e pedidos.
# Ele usa o .url público da miniatura, que é muito mais rápido.
class FotoParaLojaSerializer(serializers.ModelSerializer):
    imagem_url = serializers.SerializerMethodField()

    class Meta:
        model = Foto
        fields = ['id', 'legenda', 'preco', 'imagem_url', 'rotacao']
    
    def get_imagem_url(self, obj):
        # Lógica defensiva para evitar o ValueError
        if obj.miniatura_marca_dagua and obj.miniatura_marca_dagua.name:
            return obj.miniatura_marca_dagua.url
        # Fallback se a miniatura ainda não foi processada
        elif obj.imagem and obj.imagem.name:
             # Retorna None porque a imagem original é privada e não deve ser exposta aqui
             # O frontend deve mostrar um placeholder se a URL for nula
            return None
        return None

# --- SERIALIZERS DE CARRINHO (CORRIGIDO) ---
class ItemCarrinhoSerializer(serializers.ModelSerializer):
    foto = FotoParaLojaSerializer(read_only=True) # <-- Usa o serializer leve
    preco_item = serializers.DecimalField(source='foto.preco', max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = ItemCarrinho
        fields = ['id', 'foto', 'adicionado_em', 'preco_item']

class CarrinhoSerializer(serializers.ModelSerializer):
    itens = ItemCarrinhoSerializer(many=True, read_only=True)
    subtotal = serializers.SerializerMethodField()
    desconto = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()
    cupom = CupomSerializer(read_only=True)

    class Meta:
        model = Carrinho
        fields = ['id', 'cliente', 'criado_em', 'itens', 'subtotal', 'desconto', 'total', 'cupom']
        
    def get_subtotal(self, obj):
        return sum(item.foto.preco for item in obj.itens.all())

    def get_desconto(self, obj):
        # Lógica 1: Validação básica do cupom
        if not obj.cupom or not obj.cupom.is_valido():
             # Lógica de desconto automático por quantidade (mantida)
            if obj.itens.count() >= 5:
                subtotal = self.get_subtotal(obj)
                return round(subtotal * Decimal('0.10'), 2)
            return Decimal('0.00')

        # --- CORREÇÃO DA LÓGICA DE MARKETPLACE ---
        # O cupom pertence a um fotógrafo específico.
        # O desconto só deve ser aplicado aos itens desse fotógrafo.
        
        desconto_total = Decimal('0.00')
        fotografo_dono_cupom = obj.cupom.fotografo
        percentual = obj.cupom.desconto_percentual / Decimal('100.0')

        for item in obj.itens.all():
            # Acessa: ItemCarrinho -> Foto -> Album -> Fotógrafo
            fotografo_da_foto = item.foto.album.fotografo
            
            # Se a foto for do dono do cupom, aplica o desconto NO PREÇO DA FOTO
            if fotografo_da_foto == fotografo_dono_cupom:
                valor_desconto_item = item.foto.preco * percentual
                desconto_total += valor_desconto_item
        
        return round(desconto_total, 2)
    
    def get_total(self, obj):
        return self.get_subtotal(obj) - self.get_desconto(obj)

# --- SERIALIZERS DE PEDIDO E VENDAS (CORRIGIDO) ---
class ItemPedidoSerializer(serializers.ModelSerializer):
    foto = FotoParaLojaSerializer(read_only=True) # <-- Usa o serializer leve
    class Meta:
        model = ItemPedido
        fields = ['id', 'foto', 'preco'] # Adicionado 'id' para consistência

class PedidoSerializer(serializers.ModelSerializer):
    itens = ItemPedidoSerializer(many=True, read_only=True)
    class Meta:
        model = Pedido
        fields = ['id', 'valor_total', 'status', 'criado_em', 'itens']

class VendaFotografoSerializer(serializers.ModelSerializer):
    foto_id = serializers.IntegerField(source='foto.id')
    foto_legenda = serializers.CharField(source='foto.legenda', read_only=True)
    album_titulo = serializers.CharField(source='foto.album.titulo', read_only=True)
    data_pedido = serializers.DateTimeField(source='pedido.criado_em', read_only=True)
    cliente_email = serializers.CharField(source='pedido.cliente.email', read_only=True)
    
    class Meta:
        model = ItemPedido
        fields = [
            'id', 
            'foto_id',
            'foto_legenda',
            'album_titulo',
            'preco', 
            'data_pedido',
            'cliente_email',
        ]