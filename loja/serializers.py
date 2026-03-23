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
        desconto_total = Decimal('0.00')
        
        # 1. Primeiro verificamos os Descontos Progressivos dos Álbuns
        # Precisamos agrupar as fotos do carrinho por álbum para saber quantas o cliente tem de cada
        fotos_por_album = {}
        for item in obj.itens.all():
            album_id = item.foto.album.id
            if album_id not in fotos_por_album:
                fotos_por_album[album_id] = {
                    'album': item.foto.album,
                    'quantidade': 0,
                    'valor_soma': Decimal('0.00')
                }
            fotos_por_album[album_id]['quantidade'] += 1
            fotos_por_album[album_id]['valor_soma'] += item.foto.preco

        # Agora calculamos o desconto para cada álbum com base nas quantidades
        for dados in fotos_por_album.values():
            album = dados['album']
            qtd = dados['quantidade']
            valor_album = dados['valor_soma']
            
            melhor_desconto_pct = Decimal('0.00')
            
            # Testa os 3 níveis (Pega sempre o maior desconto alcançado)
            if album.qtd_desconto_1 > 0 and qtd >= album.qtd_desconto_1:
                melhor_desconto_pct = max(melhor_desconto_pct, album.pct_desconto_1)
            if album.qtd_desconto_2 > 0 and qtd >= album.qtd_desconto_2:
                melhor_desconto_pct = max(melhor_desconto_pct, album.pct_desconto_2)
            if album.qtd_desconto_3 > 0 and qtd >= album.qtd_desconto_3:
                melhor_desconto_pct = max(melhor_desconto_pct, album.pct_desconto_3)
            
            if melhor_desconto_pct > 0:
                desconto_album = valor_album * (melhor_desconto_pct / Decimal('100.0'))
                desconto_total += desconto_album

        # 2. Depois aplicamos a lógica do Cupom (se existir e for válido)
        # O Cupom se soma aos descontos de volume, pois o cliente merece!
        if obj.cupom and obj.cupom.is_valido():
            fotografo_dono_cupom = obj.cupom.fotografo
            percentual_cupom = obj.cupom.desconto_percentual / Decimal('100.0')

            for item in obj.itens.all():
                fotografo_da_foto = item.foto.album.fotografo
                if fotografo_da_foto == fotografo_dono_cupom:
                    valor_desconto_item = item.foto.preco * percentual_cupom
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