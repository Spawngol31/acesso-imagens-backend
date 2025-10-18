# loja/serializers.py
from rest_framework import serializers
from .models import Carrinho, ItemCarrinho, Pedido, ItemPedido, Cupom
from galeria.serializers import FotoSerializer
from galeria.models import Album, Foto
from decimal import Decimal

class CupomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cupom
        fields = ['id', 'codigo', 'desconto_percentual', 'ativo', 'data_validade']

class FotoItemSerializer(serializers.ModelSerializer):
    imagem_url = serializers.URLField(source='miniatura_marca_dagua.url', read_only=True)
    
    class Meta:
        model = Foto
        fields = ['id', 'legenda', 'imagem_url', 'rotacao']

class ItemCarrinhoSerializer(serializers.ModelSerializer):
    foto = FotoSerializer(read_only=True)
    preco_item = serializers.SerializerMethodField()

    class Meta:
        model = ItemCarrinho
        fields = ['id', 'foto', 'adicionado_em', 'preco_item']

    def get_preco_item(self, obj):
        # Agora busca o preço diretamente da foto associada
        return obj.foto.preco

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
        # Agora soma o preço de cada foto individualmente
        return sum(item.foto.preco for item in obj.itens.all())

    def get_desconto(self, obj):
        if obj.cupom and obj.cupom.is_valido():
            subtotal = self.get_subtotal(obj)
            desconto_cupom = subtotal * (obj.cupom.desconto_percentual / Decimal('100.0'))
            return round(desconto_cupom, 2)
    
        quantidade_fotos = obj.itens.count()
        if quantidade_fotos >= 5:
            subtotal = self.get_subtotal(obj)
            desconto = subtotal * Decimal('0.10')
            return round(desconto, 2)
        
        return Decimal('0.00')
    
    def get_total(self, obj):
        subtotal = self.get_subtotal(obj)
        desconto = self.get_desconto(obj)
        return subtotal - desconto

# --- Serializers para Pedidos (que estavam faltando as importações) ---

class ItemPedidoSerializer(serializers.ModelSerializer):
    foto = FotoSerializer(read_only=True)
    class Meta:
        model = ItemPedido
        fields = ['foto', 'preco']

class PedidoSerializer(serializers.ModelSerializer):
    itens = ItemPedidoSerializer(many=True, read_only=True)
    class Meta:
        model = Pedido
        fields = ['id', 'valor_total', 'status', 'criado_em', 'itens']

class VendaFotografoSerializer(serializers.ModelSerializer):
    """
    Serializer para exibir os detalhes de um item de venda
    para o painel do fotógrafo.
    """
    # Usamos 'source' para navegar pelas relações dos modelos
    foto_id = serializers.IntegerField(source='foto.id')
    foto_legenda = serializers.CharField(source='foto.legenda', read_only=True)
    album_titulo = serializers.CharField(source='foto.album.titulo', read_only=True)
    data_pedido = serializers.DateTimeField(source='pedido.criado_em', read_only=True)
    cliente_email = serializers.CharField(source='pedido.cliente.email', read_only=True)
    
    class Meta:
        model = ItemPedido
        fields = [
            'id', # ID do item do pedido
            'foto_id',
            'foto_legenda',
            'album_titulo',
            'preco', # Preço que a foto foi vendida
            'data_pedido',
            'cliente_email', # Para o fotógrafo saber quem comprou
        ]




