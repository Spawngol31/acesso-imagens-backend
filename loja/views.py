from django.shortcuts import render
from django.shortcuts import get_object_or_404

# loja/views.py
import os
import stripe
import boto3
from botocore.exceptions import ClientError
from django.db.models import Sum, Count, F, Q
from django.conf import settings
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from .permissions import IsCliente
from contas.permissions import IsAdminUser
from contas.models import Usuario
from galeria.models import Foto
from galeria.permissions import IsFotografo
from .models import Carrinho, ItemCarrinho, Foto, Pedido, ItemPedido, FotoComprada
from .serializers import CarrinhoSerializer, PedidoSerializer, VendaFotografoSerializer
from rest_framework import viewsets
from .models import Cupom
from .serializers import CupomSerializer

stripe.api_key = settings.STRIPE_SECRET_KEY

class CarrinhoView(APIView):
    permission_classes = [IsAuthenticated, IsCliente]

    def get(self, request):
        """Visualizar o carrinho do cliente logado."""
        # get_or_create garante que um carrinho exista para o cliente
        carrinho, created = Carrinho.objects.get_or_create(cliente=request.user)
        serializer = CarrinhoSerializer(carrinho, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        """Adicionar uma foto ao carrinho."""
        foto_id = request.data.get('foto_id')
        if not foto_id:
            return Response({"error": "foto_id é obrigatório."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            foto = Foto.objects.get(id=foto_id)
        except Foto.DoesNotExist:
            return Response({"error": "Foto não encontrada."}, status=status.HTTP_404_NOT_FOUND)

        carrinho, created = Carrinho.objects.get_or_create(cliente=request.user)

        # create_or_get para evitar duplicatas
        item, item_created = ItemCarrinho.objects.get_or_create(carrinho=carrinho, foto=foto)

        if not item_created:
            return Response({"message": "Esta foto já está no seu carrinho."}, status=status.HTTP_200_OK)

        serializer = CarrinhoSerializer(carrinho, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def delete(self, request):
        """Remover um item do carrinho."""
        item_id = request.data.get('item_id')
        if not item_id:
            return Response({"error": "item_id é obrigatório."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Garante que o item a ser deletado pertence ao carrinho do usuário logado
            item = ItemCarrinho.objects.get(id=item_id, carrinho__cliente=request.user)
            item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ItemCarrinho.DoesNotExist:
            return Response({"error": "Item não encontrado no seu carrinho."}, status=status.HTTP_404_NOT_FOUND)

class CheckoutView(APIView):
    permission_classes = [IsAuthenticated, IsCliente]

    def post(self, request):
        carrinho = Carrinho.objects.filter(cliente=request.user).first()
        if not carrinho or not carrinho.itens.exists():
            return Response({"error": "Seu carrinho está vazio."}, status=status.HTTP_400_BAD_REQUEST)

        # Reutiliza o serializer para calcular o total
        carrinho_serializer = CarrinhoSerializer(carrinho, context={'request': request})
        total = int(carrinho_serializer.data['total'] * 100) # Stripe usa centavos
        try:
            # Cria um Pedido com status pendente
            pedido = Pedido.objects.create(
                cliente=request.user,
                valor_total=total / 100,
                status=Pedido.StatusPedido.PENDENTE,
                # stripe_payment_intent_id = "" # Será preenchido abaixo
            )

            # 2. Em seguida, crie a Intenção de Pagamento no Stripe, passando o ID do nosso pedido
            #    para que possamos encontrá-lo no webhook.
            payment_intent = stripe.PaymentIntent.create(
                amount=total,
                currency='brl',
                metadata={'pedido_id': pedido.id}
            )

            # 3. AGORA, atualize nosso pedido com o ID único gerado pelo Stripe.
            pedido.stripe_payment_intent_id = payment_intent.id
            pedido.save()

            # Cria os Itens do Pedido a partir do carrinho
            for item_carrinho in carrinho.itens.all():
                ItemPedido.objects.create(
                    pedido=pedido,
                    foto=item_carrinho.foto,
                    preco=item_carrinho.foto.preco
                )

            return Response({
                'clientSecret': payment_intent.client_secret
            })
        
        except Exception as e:
                # Se algo der errado, podemos deletar o pedido pendente que foi criado.
            if 'pedido' in locals() and pedido.status == Pedido.StatusPedido.PENDENTE:
                    pedido.delete()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            # Cria a Intenção de Pagamento no Stripe
            payment_intent = stripe.PaymentIntent.create(
                amount=total,
                currency='brl',
                metadata={'pedido_id': pedido.id}
            )

            # Atualiza nosso pedido com o ID do Stripe
            pedido.stripe_payment_intent_id = payment_intent.id
            pedido.save()

            return Response({
                'clientSecret': payment_intent.client_secret
            })
        except Exception as e:
            pedido.status = Pedido.StatusPedido.FALHOU
            pedido.save()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class StripeWebhookView(APIView):
    permission_classes = [AllowAny] # Webhooks não usam autenticação de usuário

    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
        event = None

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, endpoint_secret
            )
        except ValueError as e: # Payload inválido
            return Response(status=status.HTTP_400_BAD_REQUEST)
        except stripe.error.SignatureVerificationError as e: # Assinatura inválida
            return Response(status=status.HTTP_400_BAD_REQUEST)

        # Lidando com o evento de sucesso no pagamento
        if event['type'] == 'payment_intent.succeeded':
            payment_intent = event['data']['object']
            pedido_id = payment_intent['metadata']['pedido_id']

            try:
                pedido = Pedido.objects.get(id=pedido_id)
                # ATUALIZA O STATUS DO PEDIDO PARA PAGO
                if pedido.status == Pedido.StatusPedido.PAGO:
                        return Response(status=status.HTTP_200_OK)
                pedido.status = Pedido.StatusPedido.PAGO
                pedido.save()

                # LIBERA O ACESSO ÀS FOTOS COMPRADAS
                for item_pedido in pedido.itens.all():
                    FotoComprada.objects.create(
                        cliente=pedido.cliente,
                        foto=item_pedido.foto
                    )

                # LIMPA O CARRINHO DO CLIENTE
                ItemCarrinho.objects.filter(carrinho__cliente=pedido.cliente).delete()

            except Pedido.DoesNotExist:
                return Response({"error": "Pedido não encontrado"}, status=status.HTTP_404_NOT_FOUND)

        elif event['type'] == 'payment_intent.payment_failed':
            payment_intent = event['data']['object']
            pedido_id = payment_intent['metadata']['pedido_id']
            pedido = Pedido.objects.get(id=pedido_id)
            pedido.status = Pedido.StatusPedido.FALHOU
            pedido.save()

        return Response(status=status.HTTP_200_OK)

class MinhasComprasView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsCliente]
    serializer_class = PedidoSerializer # (Vamos criar este serializer em breve)

    def get_queryset(self):
        return Pedido.objects.filter(cliente=self.request.user, status=Pedido.StatusPedido.PAGO)

class DownloadFotoView(APIView):
    permission_classes = [IsAuthenticated, IsCliente]

    def get(self, request, foto_id):
        compra_valida = FotoComprada.objects.filter(
            cliente=request.user,
            foto_id=foto_id,
            data_expiracao__gte=timezone.now()
        ).exists()

        if not compra_valida:
            return Response(
                {"error": "Permissão negada ou acesso expirado."},
                status=status.HTTP_403_FORBIDDEN
            )

        foto = get_object_or_404(Foto, pk=foto_id)

        # --- LÓGICA CORRETA E FINAL PARA OBTER A CHAVE DO S3 ---
        # O .name guarda o caminho relativo ao 'location' do storage.
        # Ex: 'fotos/2025/10/08/imagem.jpg'
        relative_path = foto.imagem.name
        
        # O .storage.location dá-nos o prefixo da pasta. Ex: 'media_private'
        storage_location = foto.imagem.storage.location
        
        # Juntamos os dois para ter a chave completa e correta no S3
        full_key = f"{storage_location}/{relative_path}"
        # ----------------------------------------------------

        try:
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_S3_REGION_NAME,
                config=boto3.session.Config(signature_version='s3v4')
            )
            
            file_name = os.path.basename(full_key)
            params = {
                'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                'Key': full_key, # Usamos a chave completa e correta
                'ResponseContentDisposition': f'attachment; filename="{file_name}"'
            }

            download_url = s3_client.generate_presigned_url('get_object', Params=params, ExpiresIn=300)
            return Response({'download_url': download_url})

        except ClientError as e:
            print(f"ERRO ao gerar URL de download: {e}")
            return Response({"error": "Erro ao gerar link de download."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VendasFotografoView(generics.ListAPIView):
    """
    API endpoint que lista todos os itens de fotos vendidos
    pertencentes ao fotógrafo logado.
    """
    serializer_class = VendaFotografoSerializer
    permission_classes = [IsAuthenticated, IsFotografo]

    def get_queryset(self):
        """
        Filtra os Itens de Pedido para retornar apenas aqueles
        cujas fotos pertencem a álbuns do fotógrafo logado.
        
        A consulta navega de ItemPedido -> Foto -> Album -> Fotografo.
        """
        usuario_logado = self.request.user
        return ItemPedido.objects.filter(
            pedido__status=Pedido.StatusPedido.PAGO, # Mostra apenas vendas confirmadas
            foto__album__fotografo=usuario_logado
        ).order_by('-pedido__criado_em') # Ordena pelas vendas mais recentes

class CupomViewSet(viewsets.ModelViewSet):
    serializer_class = CupomSerializer
    permission_classes = [IsAuthenticated, IsFotografo]

    def get_queryset(self):
        return Cupom.objects.filter(fotografo=self.request.user)

    def perform_create(self, serializer):
        serializer.save(fotografo=self.request.user)

class AplicarCupomView(APIView):
    permission_classes = [IsAuthenticated, IsCliente]

    def post(self, request):
        codigo = request.data.get('codigo')
        carrinho = Carrinho.objects.get(cliente=request.user)

        # --- LÓGICA DE REMOÇÃO ---
        # Se nenhum código for enviado, o utilizador quer remover o cupom atual.
        if not codigo:
            carrinho.cupom = None
            carrinho.save()
            serializer = CarrinhoSerializer(carrinho, context={'request': request})
            return Response(serializer.data)
        # -------------------------

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
    
class AdminStatsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        # 1. Totais Gerais
        pedidos_pagos = Pedido.objects.filter(status=Pedido.StatusPedido.PAGO)
        total_revenue = pedidos_pagos.aggregate(total=Sum('valor_total'))['total'] or 0
        total_sales_count = ItemPedido.objects.filter(pedido__status=Pedido.StatusPedido.PAGO).count()
        total_users = Usuario.objects.count()
        total_photographers = Usuario.objects.filter(papel=Usuario.Papel.FOTOGRAFO).count()

        # 2. Top 5 Fotógrafos por Vendas
        top_fotografos = Usuario.objects.filter(
            papel=Usuario.Papel.FOTOGRAFO,
            albuns__fotos__itempedido__pedido__status=Pedido.StatusPedido.PAGO
        ).annotate(
            total_vendido=Sum('albuns__fotos__itempedido__preco')
        ).order_by('-total_vendido').values(
            'id', 'nome_completo', 'email', 'total_vendido'
        )[:5]

        # 3. Top 5 Fotos Mais Vendidas
        top_fotos = Foto.objects.filter(
            itempedido__pedido__status=Pedido.StatusPedido.PAGO
        ).annotate(
            num_vendas=Count('itempedido')
        ).order_by('-num_vendas').values(
            'id', 'legenda', 'preco', 'album__fotografo__nome_completo', 'num_vendas'
        )[:5]

        # Monta a resposta final
        data = {
            'geral': {
                'faturacao_total': total_revenue,
                'fotos_vendidas_total': total_sales_count,
                'utilizadores_total': total_users,
                'fotografos_total': total_photographers,
            },
            'top_fotografos': list(top_fotografos),
            'top_fotos': list(top_fotos),
        }
        
        return Response(data)