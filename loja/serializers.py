# loja/serializers.py

from decimal import Decimal
from rest_framework import serializers
from .models import Carrinho, ItemCarrinho, Pedido, ItemPedido, Cupom, PropostaCompra
from galeria.models import Foto, Video
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
    album_titulo = serializers.CharField(source='album.titulo', read_only=True) # <-- NOVO

    class Meta:
        model = Foto
        # Adicione 'album' e 'album_titulo' na lista
        fields = ['id', 'legenda', 'preco', 'imagem_url', 'rotacao', 'album', 'album_titulo'] 
    
    def get_imagem_url(self, obj):
        if obj.miniatura_marca_dagua and obj.miniatura_marca_dagua.name:
            return obj.miniatura_marca_dagua.url
        elif obj.imagem and obj.imagem.name:
            return None
        return None

# --- NOVO SERIALIZER PARA VÍDEOS (OTIMIZADO) ---
class VideoParaLojaSerializer(serializers.ModelSerializer):
    miniatura_url = serializers.SerializerMethodField()
    album_titulo = serializers.CharField(source='album.titulo', read_only=True)

    class Meta:
        model = Video
        fields = ['id', 'titulo', 'preco', 'miniatura_url', 'album', 'album_titulo']
    
    def get_miniatura_url(self, obj):
        if obj.miniatura and obj.miniatura.name:
            return obj.miniatura.url
        return None

# --- SERIALIZERS DE CARRINHO (CORRIGIDO) ---
class ItemCarrinhoSerializer(serializers.ModelSerializer):
    foto = FotoParaLojaSerializer(read_only=True) 
    video = VideoParaLojaSerializer(read_only=True) # <-- Adicionado
    preco_item = serializers.SerializerMethodField()

    class Meta:
        model = ItemCarrinho
        fields = ['id', 'foto', 'video', 'adicionado_em', 'preco_item'] # <-- 'video' adicionado

    def get_preco_item(self, obj):
        # Retorna o preço dependendo do tipo de mídia que foi adicionada
        if obj.foto: return obj.foto.preco
        if obj.video: return obj.video.preco
        return Decimal('0.00')

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
        total = Decimal('0.00')
        for item in obj.itens.all():
            if item.foto:
                total += item.foto.preco
            elif item.video:
                total += item.video.preco
        return round(total, 2)

    def get_desconto(self, obj):
        desconto_total = Decimal('0.00')
        
        # 1. Agrupar mídias (Fotos ou Vídeos) por álbum
        fotos_por_album = {}
        for item in obj.itens.all():
            media = item.foto or item.video # Pega o que não estiver vazio
            if not media: continue

            album_id = media.album.id
            if album_id not in fotos_por_album:
                fotos_por_album[album_id] = {
                    'album': media.album,
                    'quantidade': 0,
                    'valor_soma': Decimal('0.00')
                }
            fotos_por_album[album_id]['quantidade'] += 1
            fotos_por_album[album_id]['valor_soma'] += media.preco

        # Agora calculamos o desconto para cada álbum com base nas quantidades
        for dados in fotos_por_album.values():
            album = dados['album']
            qtd = dados['quantidade']
            valor_album = dados['valor_soma']
            
            # --- 🚀 MÁGICA DA PROPOSTA E CONTRAPROPOSTA ACEITA ---
            proposta_aceita = PropostaCompra.objects.filter(
                cliente=obj.cliente, 
                album=album, 
                status__in=['ACEITA', 'CONTRAPROPOSTA_ACEITA'] # Funciona para as duas!
            ).order_by('-id').first() 

            desconto_proposta = Decimal('0.00')
            
            if proposta_aceita:
                qtd_fotos_exigida = proposta_aceita.quantidade_fotos
                qtd_videos_exigida = proposta_aceita.quantidade_videos
                qtd_total_exigida = qtd_fotos_exigida + qtd_videos_exigida

                # Verifica quantas fotos e vídeos o cliente colocou no carrinho deste álbum
                qtd_fotos_carrinho = sum(1 for i in obj.itens.all() if i.foto and i.foto.album.id == album.id)
                qtd_videos_carrinho = sum(1 for i in obj.itens.all() if i.video and i.video.album.id == album.id)
                
                # Só aplica o desconto se ele cumprir a quantidade prometida de FOTOS e de VÍDEOS
                if qtd_fotos_carrinho >= qtd_fotos_exigida and qtd_videos_carrinho >= qtd_videos_exigida:
                    preco_medio = valor_album / Decimal(qtd_fotos_carrinho + qtd_videos_carrinho)
                    valor_normal_dos_itens_negociados = preco_medio * Decimal(qtd_total_exigida)
                    
                    # Se foi uma contra-proposta, usa o valor dela. Se não, usa o valor original do cliente.
                    valor_acordado = proposta_aceita.valor_contraproposta if proposta_aceita.status == 'CONTRAPROPOSTA_ACEITA' else proposta_aceita.valor_oferecido
                    
                    if valor_normal_dos_itens_negociados > valor_acordado:
                        desconto_proposta = valor_normal_dos_itens_negociados - valor_acordado
            
            # --- DESCONTOS PROGRESSIVOS ---
            melhor_desconto_pct = Decimal('0.00')
            if album.qtd_desconto_1 > 0 and qtd >= album.qtd_desconto_1:
                melhor_desconto_pct = max(melhor_desconto_pct, album.pct_desconto_1)
            if album.qtd_desconto_2 > 0 and qtd >= album.qtd_desconto_2:
                melhor_desconto_pct = max(melhor_desconto_pct, album.pct_desconto_2)
            if album.qtd_desconto_3 > 0 and qtd >= album.qtd_desconto_3:
                melhor_desconto_pct = max(melhor_desconto_pct, album.pct_desconto_3)
            
            desconto_progressivo = Decimal('0.00')
            if melhor_desconto_pct > 0:
                desconto_progressivo = valor_album * (melhor_desconto_pct / Decimal('100.0'))

            desconto_album = max(desconto_proposta, desconto_progressivo)
            desconto_total += desconto_album

        # 2. Depois aplicamos a lógica do Cupom (se existir e for válido)
        if obj.cupom and obj.cupom.is_valido():
            fotografo_dono_cupom = obj.cupom.fotografo
            percentual_cupom = obj.cupom.desconto_percentual / Decimal('100.0')

            for item in obj.itens.all():
                media = item.foto or item.video
                if not media: continue

                fotografo_da_foto = media.album.fotografo
                if fotografo_da_foto == fotografo_dono_cupom:
                    valor_desconto_item = media.preco * percentual_cupom
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

class PropostaCompraSerializer(serializers.ModelSerializer):
    cliente_nome = serializers.CharField(source='cliente.nome_completo', read_only=True)
    cliente_email = serializers.CharField(source='cliente.email', read_only=True)
    album_titulo = serializers.CharField(source='album.titulo', read_only=True)

    class Meta:
        model = PropostaCompra
        fields = [
            'id', 'cliente', 'cliente_nome', 'cliente_email', 
            'album', 'album_titulo', 'quantidade_fotos', 'quantidade_videos', 
            'valor_oferecido', 'valor_contraproposta', 'status', 'criado_em'
        ]
        read_only_fields = ['id', 'cliente', 'status', 'criado_em']