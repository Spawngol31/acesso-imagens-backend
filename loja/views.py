# loja/views.py

import os
import stripe
import boto3
from botocore.exceptions import ClientError
from decimal import Decimal
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Sum, Count

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets, generics
from rest_framework.permissions import IsAuthenticated, AllowAny

from contas.permissions import IsCliente, IsFotografoOrAdmin, IsAdminUser
from .models import Carrinho, ItemCarrinho, Pedido, ItemPedido, Cupom, FotoComprada
from galeria.models import Foto
from contas.models import Usuario

# Importa os serializers do próprio app 'loja'
from .serializers import (
    CarrinhoSerializer, 
    PedidoSerializer, 
    VendaFotografoSerializer, 
    CupomSerializer
)

# --- VIEWS DO FLUXO DE COMPRA DO CLIENTE ---

class CarrinhoView(APIView):
    permission_classes = [IsAuthenticated, IsCliente]

    def get(self, request):
        carrinho, _ = Carrinho.objects.get_or_create(cliente=request.user)
        serializer = CarrinhoSerializer(carrinho, context={'request': request})
        return Response(serializer.data)
    
    def post(self, request):
        carrinho, _ = Carrinho.objects.get_or_create(cliente=request.user)
        foto_id = request.data.get('foto_id')
        foto = get_object_or_404(Foto, pk=foto_id)
        # Verifica se o item já está no carrinho
        if ItemCarrinho.objects.filter(carrinho=carrinho, foto=foto).exists():
            return Response({"error": "Esta foto já está no seu carrinho."}, status=status.HTTP_400_BAD_REQUEST)
        ItemCarrinho.objects.create(carrinho=carrinho, foto=foto)
        serializer = CarrinhoSerializer(carrinho, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    def delete(self, request):
        item_id = request.data.get('item_id')
        item = get_object_or_404(ItemCarrinho, pk=item_id, carrinho__cliente=request.user)
        item.delete()
        carrinho = Carrinho.objects.get(cliente=request.user)
        serializer = CarrinhoSerializer(carrinho, context={'request': request})
        return Response(serializer.data)

class AplicarCupomView(APIView):
    permission_classes = [IsAuthenticated, IsCliente]

    def post(self, request):
        codigo = request.data.get('codigo')
        carrinho = Carrinho.objects.get(cliente=request.user)
        if not codigo:
            carrinho.cupom = None
            carrinho.save()
            serializer = CarrinhoSerializer(carrinho, context={'request': request})
            return Response(serializer.data)
        try:
            cupom = Cupom.objects.get(codigo__iexact=codigo)
        except Cupom.DoesNotExist:
            return Response({"error": "Cupom inválido."}, status=status.HTTP_404_NOT_FOUND)
        if not cupom.is_valido():
            return Response({"error": "Este cupom não é mais válido."}, status=status.HTTP_400_BAD_REQUEST)
        primeiro_item = carrinho.itens.first()
        if primeiro_item and cupom.fotografo != primeiro_item.foto.album.fotografo:
            return Response({"error": "Este cupom não é válido para os itens no seu carrinho."}, status=status.HTTP_400_BAD_REQUEST)
        carrinho.cupom = cupom
        carrinho.save()
        serializer = CarrinhoSerializer(carrinho, context={'request': request})
        return Response(serializer.data)

class CheckoutView(APIView):
    permission_classes = [IsAuthenticated, IsCliente]
    
    def post(self, request):
        carrinho = Carrinho.objects.get(cliente=request.user)
        if not carrinho.itens.exists():
            return Response({"error": "Seu carrinho está vazio."}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer_carrinho = CarrinhoSerializer(carrinho, context={'request': request})
        total = int(serializer_carrinho.data.get('total') * 100) # Usa o total serializado

        if total <= 0:
             return Response({"error": "O valor total do pedido deve ser positivo."}, status=status.HTTP_400_BAD_REQUEST)

        pedido = Pedido.objects.create(
            cliente=request.user,
            valor_total=Decimal(total / 100)
        )
        for item_carrinho in carrinho.itens.all():
            ItemPedido.objects.create(
                pedido=pedido,
                foto=item_carrinho.foto,
                preco=item_carrinho.foto.preco
            )
        
        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            payment_intent = stripe.PaymentIntent.create(
                amount=total,
                currency='brl',
                metadata={'pedido_id': pedido.id}
            )
            return Response({
                'clientSecret': payment_intent.client_secret,
                'pedidoId': pedido.id
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class StripeWebhookView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

        # --- MELHORIA DE SEGURANÇA ---
        if not endpoint_secret:
            print("!!! ERRO DE SEGURANÇA: STRIPE_WEBHOOK_SECRET não está definido !!!")
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        event = None
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        except (ValueError, stripe.error.SignatureVerificationError) as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        if event['type'] == 'payment_intent.succeeded':
            payment_intent = event['data']['object']
            pedido_id = payment_intent['metadata']['pedido_id']
            try:
                pedido = Pedido.objects.get(id=pedido_id)
                if pedido.status == Pedido.StatusPedido.PAGO:
                    return Response(status=status.HTTP_200_OK)
                pedido.status = Pedido.StatusPedido.PAGO
                pedido.save()
                for item_pedido in pedido.itens.all():
                    FotoComprada.objects.create(cliente=pedido.cliente, foto=item_pedido.foto)
                # Limpa o carrinho do cliente após a compra
                ItemCarrinho.objects.filter(carrinho__cliente=pedido.cliente).delete()
            except Pedido.DoesNotExist:
                return Response({"error": "Pedido não encontrado"}, status=status.HTTP_404_NOT_FOUND)
        
        return Response(status=status.HTTP_200_OK)

class MinhasComprasView(generics.ListAPIView):
    serializer_class = PedidoSerializer
    permission_classes = [IsAuthenticated, IsCliente]

    def get_queryset(self):
        return Pedido.objects.filter(cliente=self.request.user, status=Pedido.StatusPedido.PAGO).order_by('-criado_em')

class DownloadFotoView(APIView):
    permission_classes = [IsAuthenticated, IsCliente]

    def get(self, request, foto_id):
        compra_valida = FotoComprada.objects.filter(cliente=request.user, foto_id=foto_id, data_expiracao__gte=timezone.now()).exists()
        if not compra_valida:
            return Response({"error": "Permissão negada ou acesso expirado."}, status=status.HTTP_403_FORBIDDEN)
        
        foto = get_object_or_404(Foto, pk=foto_id)
        try:
            relative_path = foto.imagem.name
            storage_location = foto.imagem.storage.location
            full_key = f"{storage_location}/{relative_path}"
            
            s3_client = boto3.client('s3', aws_access_key_id=settings.AWS_ACCESS_KEY_ID, aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY, region_name=settings.AWS_S3_REGION_NAME, config=boto3.session.Config(signature_version='s3v4'))
            file_name = os.path.basename(full_key)
            params = {'Bucket': settings.AWS_STORAGE_BUCKET_NAME, 'Key': full_key, 'ResponseContentDisposition': f'attachment; filename="{file_name}"'}
            download_url = s3_client.generate_presigned_url('get_object', Params=params, ExpiresIn=300)
            return Response({'download_url': download_url})
        except Exception as e:
            print(f"ERRO ao gerar URL de download: {e}")
            return Response({"error": "Erro ao gerar link de download."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# --- VIEWS DOS PAINÉIS ---

class VendasFotografoView(generics.ListAPIView):
    serializer_class = VendaFotografoSerializer
    permission_classes = [IsAuthenticated, IsFotografoOrAdmin]

    def get_queryset(self):
        if self.request.user.papel == 'ADMIN':
            return ItemPedido.objects.filter(pedido__status=Pedido.StatusPedido.PAGO).order_by('-pedido__criado_em')
        return ItemPedido.objects.filter(foto__album__fotografo=self.request.user, pedido__status=Pedido.StatusPedido.PAGO).order_by('-pedido__criado_em')

class CupomViewSet(viewsets.ModelViewSet):
    serializer_class = CupomSerializer
    permission_classes = [IsAuthenticated, IsFotografoOrAdmin]

    def get_queryset(self):
        if self.request.user.papel == 'ADMIN':
            return Cupom.objects.all()
        return Cupom.objects.filter(fotografo=self.request.user)

    def perform_create(self, serializer):
        # --- LÓGICA DE CRIAÇÃO CORRIGIDA ---
        # A lógica de atribuir o fotógrafo deve ser tratada no frontend.
        # Aqui, apenas salvamos o que o frontend nos envia.
        # No entanto, se o utilizador for um fotógrafo, forçamos que ele seja o dono.
        if self.request.user.papel == Usuario.Papel.FOTOGRAFO:
            serializer.save(fotografo=self.request.user)
        elif self.request.user.papel == Usuario.Papel.ADMIN:
            # O Admin DEVE enviar um 'fotografo_id' no pedido.
            # Se ele não o fizer, o serializer irá falhar (o que é bom).
            serializer.save()

class AdminStatsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        pedidos_pagos = Pedido.objects.filter(status=Pedido.StatusPedido.PAGO)
        total_revenue = pedidos_pagos.aggregate(total=Sum('valor_total'))['total'] or 0
        total_sales_count = ItemPedido.objects.filter(pedido__status=Pedido.StatusPedido.PAGO).count()
        total_users = Usuario.objects.count()
        total_photographers = Usuario.objects.filter(papel=Usuario.Papel.FOTOGRAFO).count()
        top_fotografos = Usuario.objects.filter(papel=Usuario.Papel.FOTOGRAFO, albuns__fotos__itempedido__pedido__status=Pedido.StatusPedido.PAGO).annotate(total_vendido=Sum('albuns__fotos__itempedido__preco')).order_by('-total_vendido').values('id', 'nome_completo', 'email', 'total_vendido')[:5]
        top_fotos = Foto.objects.filter(itempedido__pedido__status=Pedido.StatusPedido.PAGO).annotate(num_vendas=Count('itempedido')).order_by('-num_vendas').values('id', 'legenda', 'preco', 'album__fotografo__nome_completo', 'num_vendas')[:5]
        
        data = {
            'geral': {'faturacao_total': total_revenue, 'fotos_vendidas_total': total_sales_count, 'utilizadores_total': total_users, 'fotografos_total': total_photographers},
            'top_fotografos': list(top_fotografos),
            'top_fotos': list(top_fotos),
        }
        return Response(data)