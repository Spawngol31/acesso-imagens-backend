# loja/models.py
from django.db import models
from django.utils import timezone
from datetime import timedelta
from contas.models import Usuario
from galeria.models import Foto

class Carrinho(models.Model):
    # Usamos OneToOneField para garantir que cada cliente tenha apenas um carrinho.
    cliente = models.OneToOneField(Usuario, on_delete=models.CASCADE, related_name='carrinho')
    criado_em = models.DateTimeField(auto_now_add=True)
    cupom = models.ForeignKey('Cupom', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Carrinho de {self.cliente.email}"

class ItemCarrinho(models.Model):
    carrinho = models.ForeignKey(Carrinho, on_delete=models.CASCADE, related_name='itens')
    foto = models.ForeignKey(Foto, on_delete=models.CASCADE)
    adicionado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Garante que a mesma foto não possa ser adicionada duas vezes no mesmo carrinho
        unique_together = ('carrinho', 'foto')

    def __str__(self):
        return f"Foto {self.foto.id} no {self.carrinho}"
    

class Pedido(models.Model):
    class StatusPedido(models.TextChoices):
            PENDENTE = 'PENDENTE', 'Pendente'
            PAGO = 'PAGO', 'Pago'
            FALHOU = 'FALHOU', 'Falhou'

    cliente = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, related_name='pedidos')
    valor_total = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=StatusPedido.choices, default=StatusPedido.PENDENTE)
    stripe_payment_intent_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        # Verifica se o cliente existe antes de tentar aceder ao seu email
        if self.cliente:
            return f"Pedido {self.id} - {self.cliente.email}"
        return f"Pedido {self.id} - (Cliente Apagado)"

class ItemPedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='itens')
    foto = models.ForeignKey(Foto, on_delete=models.PROTECT) # PROTECT para não deletar uma foto já comprada
    preco = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"Item do Pedido {self.pedido.id} - Foto {self.foto.id}"

class FotoComprada(models.Model):
    cliente = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='fotos_compradas')
    foto = models.ForeignKey(Foto, on_delete=models.CASCADE)
    data_compra = models.DateTimeField(auto_now_add=True)
    data_expiracao = models.DateTimeField()

    def save(self, *args, **kwargs):
        if not self.id: # Só define a data de expiração na criação
            self.data_expiracao = timezone.now() + timedelta(days=60)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.cliente.email} comprou a Foto {self.foto.id}"

    @property
    def is_valida(self):
        return timezone.now() < self.data_expiracao
    
class Cupom(models.Model):
    codigo = models.CharField(max_length=50, unique=True)
    desconto_percentual = models.DecimalField(max_digits=5, decimal_places=2, help_text="Ex: 20.00 para 20% de desconto.")
    ativo = models.BooleanField(default=True)
    data_validade = models.DateField(blank=True, null=True)
    
    # --- CAMPO CORRIGIDO ---
    # Adicionamos null=True e blank=True para tornar o campo opcional
    fotografo = models.ForeignKey(
        Usuario, 
        on_delete=models.CASCADE, 
        related_name='cupons',
        limit_choices_to={'papel': Usuario.Papel.FOTOGRAFO},
        null=True,
        blank=True
    )

    def __str__(self):
        return self.codigo

    def is_valido(self):
        if not self.ativo:
            return False
        if self.data_validade and self.data_validade < timezone.now().date():
            return False
        return True
