# loja/views.py

import os, boto3, mercadopago
import json # Import necessário para logs
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

# --- IMPORTS DE SEGURANÇA (CORREÇÃO) ---
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from contas.permissions import IsCliente, IsFotografoOrAdmin, IsAdminUser
from .models import Carrinho, ItemCarrinho, Pedido, ItemPedido, Cupom, FotoComprada
from galeria.models import Foto
from contas.models import Usuario
from .serializers import (
    CarrinhoSerializer, PedidoSerializer, VendaFotografoSerializer, CupomSerializer
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

class MercadoPagoCheckoutView(APIView):
    permission_classes = [IsAuthenticated, IsCliente]
    
    def post(self, request):
        try:
            carrinho = Carrinho.objects.get(cliente=request.user)
            if not carrinho.itens.exists():
                return Response({"error": "Seu carrinho está vazio."}, status=status.HTTP_400_BAD_REQUEST)
            
            serializer_carrinho = CarrinhoSerializer(carrinho, context={'request': request})
            total = float(serializer_carrinho.data.get('total'))

            if total <= 0:
                return Response({"error": "O valor total do pedido deve ser positivo."}, status=status.HTTP_400_BAD_REQUEST)

            # 1. Cria o Pedido
            pedido = Pedido.objects.create(
                cliente=request.user,
                valor_total=Decimal(total)
            )
            itens_do_pedido = []
            for item_carrinho in carrinho.itens.all():
                ItemPedido.objects.create(
                    pedido=pedido,
                    foto=item_carrinho.foto,
                    preco=item_carrinho.foto.preco
                )
                itens_do_pedido.append({
                    "title": f"Foto ID: {item_carrinho.foto.id}",
                    "quantity": 1,
                    "unit_price": float(item_carrinho.foto.preco),
                    "currency_id": "BRL"
                })
            
            if not hasattr(settings, 'MP_ACCESS_TOKEN') or not settings.MP_ACCESS_TOKEN:
                raise Exception("A chave MP_ACCESS_TOKEN não está configurada.")

            sdk = mercadopago.SDK(settings.MP_ACCESS_TOKEN)

            preference_data = {
                "items": itens_do_pedido,
                "payer": {
                    "name": request.user.nome_completo,
                    "email": request.user.email,
                },
                "back_urls": {
                    "success": f"{settings.FRONTEND_URL}/minhas-compras",
                    "failure": f"{settings.FRONTEND_URL}/carrinho",
                    "pending": f"{settings.FRONTEND_URL}/minhas-compras"
                },
                # "auto_return": "approved", # Desativado para evitar erros em localhost
                "external_reference": str(pedido.id),
                "notification_url": f"{settings.BACKEND_URL}/api/webhooks/mp/",
            }
            
            preference_response = sdk.preference().create(preference_data)
            
            if preference_response.get("status") not in [200, 201]:
                 raise Exception(f"Mercado Pago recusou: {preference_response.get('response')}")

            preference = preference_response["response"]
            
            # --- CORREÇÃO AQUI: Devolvemos também o order_id ---
            return Response({
                'preference_id': preference['id'],
                'order_id': str(pedido.id) # IMPORTANTE!
            })

        except Exception as e:
            print(f"ERRO CRÍTICO NO CHECKOUT: {str(e)}")
            return Response({'error': f"Erro no servidor: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MercadoPagoProcessPaymentView(APIView):
    permission_classes = [IsAuthenticated, IsCliente]

    def post(self, request):
        try:
            payment_data = request.data
            sdk = mercadopago.SDK(settings.MP_ACCESS_TOKEN)
            
            # Garante que o email está presente
            if 'payer' not in payment_data:
                payment_data['payer'] = {}
            payment_data['payer']['email'] = request.user.email

            # --- CORREÇÃO AQUI: Força o external_reference ---
            # Se o frontend enviou o external_reference, garantimos que ele vai para o MP
            if 'external_reference' in payment_data:
                print(f"--- Processando pagamento para Pedido ID: {payment_data['external_reference']} ---")
            else:
                print("--- AVISO: external_reference (ID do Pedido) não recebido do frontend! ---")

            payment_response = sdk.payment().create(payment_data)
            payment = payment_response["response"]
            
            status_pagamento = payment.get("status")

            if status_pagamento:
                return Response(payment, status=status.HTTP_201_CREATED)
            else:
                return Response({"error": "Falha ao criar pagamento", "details": payment}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            print(f"ERRO AO PROCESSAR PAGAMENTO: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# --- VIEW DO WEBHOOK (Simplificada e Robusta) ---
@method_decorator(csrf_exempt, name='dispatch')
class MercadoPagoWebhookView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        print("\n--- WEBHOOK MERCADO PAGO RECEBIDO ---")
        topic = request.data.get("type")
        payment_id = request.data.get("data", {}).get("id")
        print(f"Tópico: {topic}, Payment ID: {payment_id}")
        
        if topic == "payment":
            try:
                sdk = mercadopago.SDK(settings.MP_ACCESS_TOKEN)
                payment_response = sdk.payment().get(payment_id)
                payment = payment_response["response"]
                
                status_pagamento = payment.get("status")
                external_ref = payment.get("external_reference")
                
                print(f"Status: {status_pagamento}, Pedido ID (Ref): {external_ref}")

                if status_pagamento == "approved":
                    if not external_ref:
                        print("ERRO CRÍTICO: Pagamento aprovado sem ID de Pedido (external_reference).")
                        return Response(status=status.HTTP_200_OK)

                    try:
                        pedido = Pedido.objects.get(id=int(external_ref))
                        
                        if pedido.status == Pedido.StatusPedido.PAGO:
                            print("Pedido já estava pago. Ignorando.")
                            return Response(status=status.HTTP_200_OK)
                        
                        print(f"Processando Pedido {pedido.id}...")
                        pedido.status = Pedido.StatusPedido.PAGO
                        pedido.save()
                        
                        for item_pedido in pedido.itens.all():
                            FotoComprada.objects.create(cliente=pedido.cliente, foto=item_pedido.foto)
                        
                        ItemCarrinho.objects.filter(carrinho__cliente=pedido.cliente).delete()
                        print(f"SUCESSO: Pedido {pedido.id} finalizado!")
                        
                    except Pedido.DoesNotExist:
                        print(f"ERRO: Pedido ID {external_ref} não encontrado.")
                        return Response(status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                print(f"ERRO NO WEBHOOK: {e}")
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
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