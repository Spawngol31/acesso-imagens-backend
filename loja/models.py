# loja/models.py

from django.db import models
from django.utils import timezone
from datetime import timedelta
from contas.models import Usuario
from galeria.models import Foto, Video, Album

class Carrinho(models.Model):
    cliente = models.OneToOneField(Usuario, on_delete=models.CASCADE, related_name='carrinho')
    criado_em = models.DateTimeField(auto_now_add=True)
    cupom = models.ForeignKey('Cupom', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Carrinho de {self.cliente.email}"

class ItemCarrinho(models.Model):
    carrinho = models.ForeignKey(Carrinho, on_delete=models.CASCADE, related_name='itens')
    # Transformamos a foto em opcional (null=True)
    foto = models.ForeignKey(Foto, on_delete=models.CASCADE, null=True, blank=True) 
    # Adicionamos a coluna do vídeo (opcional também)
    video = models.ForeignKey(Video, on_delete=models.CASCADE, null=True, blank=True) 
    adicionado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        # Pequena adaptação para mostrar corretamente no painel Admin
        if self.foto: return f"Foto {self.foto.id} no {self.carrinho}"
        if self.video: return f"Vídeo {self.video.id} no {self.carrinho}"
        return f"Item vazio no {self.carrinho}"
    

class Pedido(models.Model):
    class StatusPedido(models.TextChoices):
        PENDENTE = 'PENDENTE', 'Pendente'
        PAGO = 'PAGO', 'Pago'
        FALHOU = 'FALHOU', 'Falhou'

    cliente = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, related_name='pedidos')
    valor_total = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=StatusPedido.choices, default=StatusPedido.PENDENTE)
    id_pagamento_externo = models.CharField(
        max_length=255, 
        unique=True, 
        null=True, 
        blank=True,
        help_text="ID da transação no Mercado Pago"
    )
    metodo_pagamento = models.CharField(
        max_length=50, 
        default='MERCADO_PAGO'
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        if self.status == 'PAGO':

            from .models import FotoComprada 

            itens_do_pedido = self.itens.all() 
            
            for item in itens_do_pedido:
                
                FotoComprada.objects.get_or_create(
                    cliente=self.cliente,
                    foto=item.foto
                )

    def __str__(self):
        if self.cliente:
            return f"Pedido {self.id} - {self.cliente.email}"
        return f"Pedido {self.id} - (Cliente Apagado)"

class ItemPedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='itens')
    foto = models.ForeignKey(Foto, on_delete=models.PROTECT, null=True, blank=True) 
    video = models.ForeignKey(Video, on_delete=models.PROTECT, null=True, blank=True) 
    preco = models.DecimalField(max_digits=10, decimal_places=2)
    pago_ao_fotografo = models.BooleanField(default=False)

    # 🚀 ADICIONE ESTA FUNÇÃO PARA CORRIGIR O NOME NA TELA
    def __str__(self):
        if self.foto:
            return f"📸 Foto #{self.foto.id}"
        if self.video:
            return f"🎥 Vídeo #{self.video.id}"
        return "⚠️ Item Vazio"

class FotoComprada(models.Model):
    cliente = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='fotos_compradas')
    foto = models.ForeignKey(Foto, on_delete=models.CASCADE, null=True, blank=True)
    video = models.ForeignKey(Video, on_delete=models.CASCADE, null=True, blank=True)
    data_compra = models.DateTimeField(auto_now_add=True)
    data_expiracao = models.DateTimeField()

    def save(self, *args, **kwargs):
        if not self.id: 
            self.data_expiracao = timezone.now() + timedelta(days=60)
        super().save(*args, **kwargs)

    # 🚀 A CORREÇÃO DA FALHA 500 ESTÁ AQUI:
    def __str__(self):
        if self.foto:
            return f"{self.cliente.email} comprou a Foto #{self.foto.id}"
        elif self.video:
            return f"{self.cliente.email} comprou o Vídeo #{self.video.id}"
        return f"{self.cliente.email} comprou um item (Apagado)"

    @property
    def is_valida(self):
        return timezone.now() < self.data_expiracao
    
class Cupom(models.Model):
    codigo = models.CharField(max_length=50, unique=True)
    desconto_percentual = models.DecimalField(max_digits=5, decimal_places=2, help_text="Ex: 20.00 para 20% de desconto.")
    ativo = models.BooleanField(default=True)
    data_validade = models.DateField(blank=True, null=True)
    
    fotografo = models.ForeignKey(
        Usuario, 
        on_delete=models.CASCADE, 
        related_name='cupons',
        limit_choices_to={'papel': Usuario.Papel.FOTOGRAFO}
        # null=True, # Removido
        # blank=True # Removido
    )

    albuns = models.ManyToManyField(
        Album, # Se o model Album estiver em outro app, use 'nome_do_app.Album' ou importe a classe Album
        blank=True,
        related_name='cupons',
        help_text="Se ficar em branco, o cupom vale para TODOS os álbuns deste fotógrafo. Se selecionar álbuns, valerá apenas para os selecionados."
    )

    def __str__(self):
        return self.codigo

    def is_valido(self):
        if not self.ativo:
            return False
        if self.data_validade and self.data_validade < timezone.now().date():
            return False
        return True

    def is_valido_para_album(self, album):
        """
        Verifica se o cupom pode ser aplicado a uma foto de um determinado álbum.
        """
        if not self.is_valido():
            return False
            
        # Garante que o álbum pertence ao fotógrafo dono do cupom
        if album.fotografo != self.fotografo:
            return False
            
        # Se o fotógrafo selecionou álbuns específicos, verifica se este álbum está na lista
        if self.albuns.exists():
            return self.albuns.filter(id=album.id).exists()
            
        # Se não selecionou nenhum álbum específico, vale para qualquer álbum deste fotógrafo
        return True
    
    # --- 2. O NOVO MODELO DE RECIBOS/HISTÓRICO ---
class HistoricoPagamentoFotografo(models.Model):
    fotografo = models.ForeignKey(
        Usuario, 
        on_delete=models.CASCADE, 
        limit_choices_to={'papel': Usuario.Papel.FOTOGRAFO}
    )
    data_pagamento = models.DateTimeField(auto_now_add=True)
    valor_pago = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Para saber de que período foi esse pagamento (opcional, mas ótimo para auditoria)
    referencia_inicio = models.DateField(null=True, blank=True)
    referencia_fim = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"Pagamento R$ {self.valor_pago} para {self.fotografo.nome_completo} em {self.data_pagamento.strftime('%d/%m/%Y')}"

class PropostaCompra(models.Model):
    STATUS_CHOICES = [
        ('PENDENTE', 'Pendente (Aguardando Fotógrafo)'),
        ('ACEITA', 'Aceita pelo Fotógrafo'),
        ('RECUSADA', 'Recusada pelo Fotógrafo'),
        ('CONTRAPROPOSTA', 'Contra-proposta Enviada'),
        ('CONTRAPROPOSTA_ACEITA', 'Contra-proposta Aceita pelo Cliente'),
        ('CONTRAPROPOSTA_RECUSADA', 'Contra-proposta Recusada pelo Cliente')
    ]
    
    cliente = models.ForeignKey('contas.Usuario', on_delete=models.CASCADE, related_name='propostas_feitas')
    album = models.ForeignKey('galeria.Album', on_delete=models.CASCADE, related_name='propostas_recebidas')
    
    # Agora separamos as quantidades
    quantidade_fotos = models.PositiveIntegerField("Quantidade de Fotos", default=0)
    quantidade_videos = models.PositiveIntegerField("Quantidade de Vídeos", default=0)
    
    # Valores da negociação
    valor_oferecido = models.DecimalField("Valor Oferecido (R$)", max_digits=10, decimal_places=2)
    valor_contraproposta = models.DecimalField("Contra-proposta (R$)", max_digits=10, decimal_places=2, null=True, blank=True)
    comentario = models.TextField("Comentário do Cliente", null=True, blank=True, help_text="Mensagem opcional do cliente para o fotógrafo")
    
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='PENDENTE')
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Proposta #{self.id} | Cliente: {self.cliente.nome_completo} | R$ {self.valor_oferecido}"

class SolicitacaoSaque(models.Model):
    STATUS_CHOICES = [
        ('PENDENTE', 'Pendente (Aguardando Pagamento)'),
        ('PAGO', 'Pago'),
        ('RECUSADA', 'Recusada')
    ]
    
    fotografo = models.ForeignKey(
        Usuario, 
        on_delete=models.CASCADE, 
        related_name='saques_solicitados', 
        limit_choices_to={'papel': Usuario.Papel.FOTOGRAFO}
    )
    valor = models.DecimalField("Valor Solicitado (R$)", max_digits=10, decimal_places=2)
    chave_pix = models.CharField("Chave PIX", max_length=255, help_text="Chave PIX para recebimento")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDENTE')
    observacao = models.TextField("Observação/Motivo", blank=True, null=True, help_text="Motivo em caso de recusa ou ID de transação bancária")
    comprovante = models.FileField(upload_to='comprovantes_saque/', blank=True, null=True, help_text="Comprovante de transferência (Imagem ou PDF)")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Saque #{self.id} | {self.fotografo.nome_completo} | R$ {self.valor} | {self.status}"