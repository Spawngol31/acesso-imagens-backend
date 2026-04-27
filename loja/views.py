# loja/views.py

import csv
import os, boto3, mercadopago
import json # Import necessário para logs

from botocore.exceptions import ClientError
from decimal import Decimal

from django.core.mail import send_mail
from django.http import HttpResponse
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.db.models import Sum, Count
from django.db import transaction
from django.db.models import Q

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets, generics
from rest_framework.permissions import IsAuthenticated, AllowAny

# --- IMPORTS DE SEGURANÇA (CORREÇÃO) ---
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from contas.permissions import IsCliente, IsFotografoOrAdmin, IsAdminUser
from .models import Carrinho, ItemCarrinho, Pedido, ItemPedido, Cupom, FotoComprada, HistoricoPagamentoFotografo
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
        
        tem_foto_valida = any(item.foto.album.fotografo == cupom.fotografo for item in carrinho.itens.all())
        
        if not tem_foto_valida:
            return Response({"error": "Este cupom não é válido para nenhuma das fotos no seu carrinho."}, status=status.HTTP_400_BAD_REQUEST)
        
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
                # 1. Busca o pedido no banco para descobrir o valor REAL
                pedido = get_object_or_404(Pedido, id=payment_data['external_reference'], cliente=request.user)
                
                # 2. IGNORA o preço do frontend e FORÇA o preço do banco de dados
                payment_data['transaction_amount'] = float(pedido.valor_total)
                print(f"--- Processando pagamento para Pedido ID: {pedido.id} no valor de R$ {pedido.valor_total} ---")
            else:
                return Response({"error": "ID do pedido (external_reference) ausente."}, status=status.HTTP_400_BAD_REQUEST)

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
                
                # --- NOVIDADE: Pegamos como o cliente pagou ---
                tipo_pagamento_mp = payment.get("payment_type_id") # ex: bank_transfer, credit_card
                metodo_pagamento_mp = payment.get("payment_method_id") # ex: pix, visa, master
                
                print(f"Status: {status_pagamento}, Pedido ID (Ref): {external_ref}, Tipo: {tipo_pagamento_mp}")

                if status_pagamento == "approved":
                    if not external_ref:
                        print("ERRO CRÍTICO: Pagamento aprovado sem ID de Pedido (external_reference).")
                        return Response(status=status.HTTP_200_OK)

                    try:
                        pedido = Pedido.objects.get(id=int(external_ref))
                        
                        if pedido.status == Pedido.StatusPedido.PAGO:
                            print("Pedido já estava pago. Ignorando.")
                            return Response(status=status.HTTP_200_OK)
                        
                        valor_pago_mp = payment.get("transaction_amount")
                        if float(valor_pago_mp) < float(pedido.valor_total):
                            print(f"FRAUDE BLOQUEADA: Tentativa de pagar R$ {valor_pago_mp} num pedido de R$ {pedido.valor_total}")
                            # Retorna 200 OK pro Mercado Pago não ficar repetindo o envio, 
                            # mas NÃO aprova o pedido no nosso banco de dados.
                            return Response(status=status.HTTP_200_OK)

                        print(f"Processando Pedido {pedido.id}...")
                        
                        # --- NOVIDADE: Traduzimos e salvamos a forma de pagamento ---
                        traducao_pagamento = {
                            'bank_transfer': 'Pix',
                            'ticket': 'Boleto',
                            'credit_card': 'Cartão de Crédito',
                            'debit_card': 'Cartão de Débito',
                            'account_money': 'Saldo Mercado Pago'
                        }
                        
                        tipo_legivel = traducao_pagamento.get(tipo_pagamento_mp, "Mercado Pago")
                        
                        # Se for cartão, adicionamos a bandeira (ex: "Cartão de Crédito (VISA)")
                        if metodo_pagamento_mp and tipo_pagamento_mp in ['credit_card', 'debit_card']:
                            tipo_legivel += f" ({metodo_pagamento_mp.upper()})"
                        
                        # Atualiza o pedido com os novos dados
                        pedido.metodo_pagamento = tipo_legivel
                        pedido.status = Pedido.StatusPedido.PAGO
                        pedido.save()
                        
                        for item_pedido in pedido.itens.all():
                            FotoComprada.objects.create(cliente=pedido.cliente, foto=item_pedido.foto)
                        
                        ItemCarrinho.objects.filter(carrinho__cliente=pedido.cliente).delete()
                        print(f"SUCESSO: Pedido {pedido.id} finalizado e pago via {tipo_legivel}!")
                        
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

class EnviarFotoEmailView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, foto_id):
        user = request.user
        
        # 1. Verifica se o cliente realmente comprou esta foto (Segurança!)
        comprou = FotoComprada.objects.filter(cliente=user, foto_id=foto_id).exists()
        if not comprou:
            return Response({"error": "Você não tem permissão para baixar esta foto."}, status=403)

        try:
            foto = Foto.objects.get(id=foto_id)
            
            # 2. Pega a URL original da foto na AWS S3
            # (Use a mesma lógica que você já usa na sua view normal de download)
            url_download = foto.imagem.url 
            
            # Se você usar links temporários (presigned urls) do Boto3, gere-o aqui.
            # url_download = gerar_presigned_url(foto.imagem.name) 

            # 3. Monta o E-mail
            assunto = f"Acesso Imagens - A sua foto do álbum {foto.album.titulo} chegou!"
            
            mensagem_html = f"""
            <h2>Olá, {user.first_name or 'Cliente'}!</h2>
            <p>Você solicitou o envio da sua foto comprada na plataforma <b>Acesso Imagens</b>.</p>
            <p>Para baixar o ficheiro original em alta resolução, basta clicar no link abaixo. Ele pode ser aberto em qualquer navegador padrão (Chrome, Safari, etc).</p>
            <br>
            <a href="{url_download}" style="background-color: #6c0464; color: white; padding: 12px 20px; text-decoration: none; border-radius: 18px; font-weight: bold;">
                ⬇️ Baixar Minha Foto
            </a>
            <br><br>
            <p>Obrigado por comprar conosco!</p>
            <p>Equipe Acesso Imagens</p>
            """
            
            # 4. Dispara o E-mail
            send_mail(
                subject=assunto,
                message="Abra este e-mail num cliente que suporte HTML para ver o link de download.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=mensagem_html,
                fail_silently=False,
            )

            return Response({
                "message": "E-mail enviado com sucesso!", 
                "email_destino": user.email
            }, status=200)

        except Foto.DoesNotExist:
            return Response({"error": "Foto não encontrada."}, status=404)
        except Exception as e:
            return Response({"error": f"Erro interno: {str(e)}"}, status=500)
        
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
    
class ExportarPagamentosCSVView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        # 1. Pega TODOS os filtros que o React vai enviar
        data_inicio = request.GET.get('data_inicio')
        data_fim = request.GET.get('data_fim')
        fotografo_id = request.GET.get('fotografo_id')
        status = request.GET.get('status')
        search = request.GET.get('search')

        # 2. CORREÇÃO: Busca TODOS os itens do pedido (igual à tela)
        vendas = ItemPedido.objects.all().order_by('-pedido__criado_em')

        # 3. Aplica os filtros exatamente como na tela
        if data_inicio:
            vendas = vendas.filter(pedido__criado_em__date__gte=parse_date(data_inicio))
        if data_fim:
            vendas = vendas.filter(pedido__criado_em__date__lte=parse_date(data_fim))
        if fotografo_id:
            vendas = vendas.filter(foto__album__fotografo__id=fotografo_id)
        if status:
            vendas = vendas.filter(pedido__status=status) # Se não escolher status, traz todos (incluindo PENDENTE)
        if search:
            vendas = vendas.filter(pedido__id__icontains=search)

        # 4. Prepara o arquivo Excel (CSV)
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="relatorio_pagamentos_site.csv"'
        writer = csv.writer(response, delimiter=';')
        
        # Cabeçalho
        writer.writerow(['ID Pedido', 'Data da Venda', 'Status', 'Fotógrafo', 'ID da Foto', 'Valor da Venda (R$)', 'Comissão a Pagar (R$)'])
        
        total_geral = 0.0

        # Preenche as linhas
        for item in vendas:
            try:
                nome_fotografo = item.foto.album.fotografo.nome_completo or item.foto.album.fotografo.email
            except AttributeError:
                nome_fotografo = "Desconhecido"

            valor = float(item.preco) if item.preco else 0.0
            comissao = valor * 0.95 # A taxa do fotógrafo
            total_geral += comissao

            data_local = timezone.localtime(item.pedido.criado_em)

            writer.writerow([
                item.pedido.id,
                data_local.strftime("%d/%m/%Y %H:%M"),
                item.pedido.status,
                nome_fotografo,
                item.foto.id,
                str(f"{valor:.2f}").replace('.', ','),
                str(f"{comissao:.2f}").replace('.', ',')
            ])

        # Linha do Total Final
        writer.writerow([])
        writer.writerow(['', '', '', '', '', 'TOTAL A PAGAR:', str(f"{total_geral:.2f}").replace('.', ',')])

        return response

class AdminVendasJSONView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        # 1. Pega os filtros da URL
        data_inicio = request.GET.get('data_inicio')
        data_fim = request.GET.get('data_fim')
        fotografo_id = request.GET.get('fotografo_id')
        status = request.GET.get('status')
        search = request.GET.get('search')

        # 2. Busca todos os itens
        vendas = ItemPedido.objects.all().order_by('-pedido__criado_em')

        # 3. Aplica os filtros
        if data_inicio:
            vendas = vendas.filter(pedido__criado_em__date__gte=parse_date(data_inicio))
        if data_fim:
            vendas = vendas.filter(pedido__criado_em__date__lte=parse_date(data_fim))
        if fotografo_id:
            vendas = vendas.filter(foto__album__fotografo__id=fotografo_id)
        if status:
            vendas = vendas.filter(pedido__status=status)
        if search:
            vendas = vendas.filter(pedido__id__icontains=search)

        # --- NOVIDADE: CÁLCULO INTELIGENTE DOS TOTAIS ---
        # Só somamos para pagar se a venda estiver como PAGO pelo cliente E AINDA NÃO PAGA ao fotógrafo
        vendas_para_pagar = vendas.filter(pedido__status=Pedido.StatusPedido.PAGO, pago_ao_fotografo=False)
        total_vendas_pendentes = vendas_para_pagar.aggregate(total=Sum('preco'))['total'] or 0
        total_pagar_pendente = float(total_vendas_pendentes) * 0.95
        # ------------------------------------------------

        # Pega a lista de fotógrafos para o select do React
        fotografos_db = ItemPedido.objects.filter(foto__album__fotografo__isnull=False).values_list(
            'foto__album__fotografo__id', 
            'foto__album__fotografo__nome_completo', 
            'foto__album__fotografo__email'
        ).distinct()
        
        lista_fotografos = [{"id": f[0], "nome": f[1] or f[2]} for f in fotografos_db]

        # 5. Monta a lista para a tabela
        dados_tabela = []
        for item in vendas:
            try:
                nome_fotografo = item.foto.album.fotografo.nome_completo or item.foto.album.fotografo.email
            except AttributeError:
                nome_fotografo = "Desconhecido"
            
            data_local = timezone.localtime(item.pedido.criado_em)
            
            dados_tabela.append({
                "id": item.id,
                "pedido_id": item.pedido.id,
                "fotografo": nome_fotografo,
                "foto_id": item.foto.id,
                "data": data_local.strftime("%d/%m/%Y %H:%M"),
                "forma_pgto": getattr(item.pedido, 'metodo_pagamento', 'MERCADO_PAGO'),
                "status": item.pedido.status,
                "pago_ao_fotografo": item.pago_ao_fotografo, # <--- Enviamos a etiqueta nova!
                "valor_venda": float(item.preco) if item.preco else 0,
                "comissao": (float(item.preco) * 0.95) if item.preco else 0
            })

        return Response({
            "resumo": {
                "total_vendas": total_vendas_pendentes,
                "total_pagar": total_pagar_pendente
            },
            "resultados": dados_tabela,
            "fotografos": lista_fotografos
        })

class RegistrarPagamentoFotografoView(APIView):
    permission_classes = [IsAdminUser]

    @transaction.atomic
    def post(self, request):
        fotografo_id = request.data.get('fotografo_id')
        data_inicio = request.data.get('data_inicio')
        data_fim = request.data.get('data_fim')
        valor_pago = request.data.get('valor_pago')

        if not fotografo_id or not valor_pago:
            return Response({"erro": "Fotógrafo e valor são obrigatórios."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 1. Busca os itens que devem ser pagos
            filtros = Q(
                pedido__status=Pedido.StatusPedido.PAGO,
                foto__album__fotografo__id=fotografo_id,
                pago_ao_fotografo=False
            )

            if data_inicio:
                filtros &= Q(pedido__criado_em__date__gte=parse_date(data_inicio))
            if data_fim:
                filtros &= Q(pedido__criado_em__date__lte=parse_date(data_fim))

            itens_pendentes = ItemPedido.objects.filter(filtros)

            if not itens_pendentes.exists():
                return Response(
                    {"erro": "Nenhuma venda pendente encontrada para este filtro."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 2. Atualiza os itens (Mágica do Zerar)
            total_atualizado = itens_pendentes.update(pago_ao_fotografo=True)

            # 3. Cria o Recibo
            fotografo = Usuario.objects.get(id=fotografo_id)
            recibo = HistoricoPagamentoFotografo.objects.create(
                fotografo=fotografo,
                valor_pago=valor_pago,
                referencia_inicio=parse_date(data_inicio) if data_inicio else None,
                referencia_fim=parse_date(data_fim) if data_fim else None
            )

            return Response({
                "mensagem": "Pagamento registrado com sucesso!",
                "vendas_atualizadas": total_atualizado,
                "recibo_id": recibo.id
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"erro": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class AdminHistoricoPagamentosView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        historico = HistoricoPagamentoFotografo.objects.all().order_by('-data_pagamento')
        
        dados = []
        for rec in historico:
            data_local = timezone.localtime(rec.data_pagamento)
            dados.append({
                "id": rec.id,
                "fotografo": rec.fotografo.nome_completo or rec.fotografo.email,
                "data_pagamento": data_local.strftime("%d/%m/%Y %H:%M"),
                "valor_pago": float(rec.valor_pago),
                "referencia_inicio": rec.referencia_inicio.strftime("%d/%m/%Y") if rec.referencia_inicio else "Não filtrado",
                "referencia_fim": rec.referencia_fim.strftime("%d/%m/%Y") if rec.referencia_fim else "Não filtrado"
            })
        
        return Response(dados)
    
class FotografoVendasJSONView(APIView):
    permission_classes = [IsAuthenticated, IsFotografoOrAdmin]

    def get(self, request):
        fotografo = request.user
        data_inicio = request.GET.get('data_inicio')
        data_fim = request.GET.get('data_fim')
        status_repasse = request.GET.get('status_repasse') # Pode ser 'PENDENTE' ou 'PAGO'

        # 1. Pega APENAS as vendas deste fotógrafo onde o cliente JÁ PAGOU
        vendas = ItemPedido.objects.filter(
            foto__album__fotografo=fotografo,
            pedido__status=Pedido.StatusPedido.PAGO
        ).order_by('-pedido__criado_em')

        # 2. Aplica os filtros de data e status
        if data_inicio:
            vendas = vendas.filter(pedido__criado_em__date__gte=parse_date(data_inicio))
        if data_fim:
            vendas = vendas.filter(pedido__criado_em__date__lte=parse_date(data_fim))
        if status_repasse == 'PAGO':
            vendas = vendas.filter(pago_ao_fotografo=True)
        elif status_repasse == 'PENDENTE':
            vendas = vendas.filter(pago_ao_fotografo=False)

        # 3. Calcula os Saldos Fixos (O que ele tem a receber hoje e o que já recebeu na vida)
        saldo_pendente_db = ItemPedido.objects.filter(
            foto__album__fotografo=fotografo,
            pedido__status=Pedido.StatusPedido.PAGO,
            pago_ao_fotografo=False
        ).aggregate(total=Sum('preco'))['total'] or 0

        total_ja_recebido_db = HistoricoPagamentoFotografo.objects.filter(
            fotografo=fotografo
        ).aggregate(total=Sum('valor_pago'))['total'] or 0

        # 4. Monta a tabela
        # 4. Monta a tabela
        dados_tabela = []
        for item in vendas:
            data_local = timezone.localtime(item.pedido.criado_em)
            
            # --- TENTATIVA SEGURA DE BUSCAR O NOME ---
            nome_cliente = "Desconhecido"
            
            # 1. Verifica se o campo se chama 'cliente' (o mais comum)
            if hasattr(item.pedido, 'cliente') and item.pedido.cliente:
                nome_cliente = item.pedido.cliente.nome_completo or item.pedido.cliente.email
            
            # 2. Verifica se o campo se chama 'user'
            elif hasattr(item.pedido, 'user') and item.pedido.user:
                nome_cliente = item.pedido.user.nome_completo or item.pedido.user.email
            
            # 3. Se for apenas texto salvo no pedido (ex: compras sem login)
            elif hasattr(item.pedido, 'cliente_nome') and item.pedido.cliente_nome:
                nome_cliente = item.pedido.cliente_nome
            elif hasattr(item.pedido, 'cliente_email') and item.pedido.cliente_email:
                nome_cliente = item.pedido.cliente_email
            
            dados_tabela.append({
                "id": item.id,
                "pedido_id": item.pedido.id,
                "foto_id": item.foto.id,
                "cliente": nome_cliente,
                "data": data_local.strftime("%d/%m/%Y %H:%M"),
                "pago_ao_fotografo": item.pago_ao_fotografo,
                "valor_venda": float(item.preco) if item.preco else 0,
                "comissao": (float(item.preco) * 0.95) if item.preco else 0
            })

        return Response({
            "resumo": {
                "saldo_pendente": float(saldo_pendente_db) * 0.95,
                "total_ja_recebido": float(total_ja_recebido_db)
            },
            "resultados": dados_tabela
        })

class FotografoHistoricoPagamentosView(APIView):
    permission_classes = [IsAuthenticated, IsFotografoOrAdmin]

    def get(self, request):
        # Traz apenas os recibos deste fotógrafo específico
        historico = HistoricoPagamentoFotografo.objects.filter(fotografo=request.user).order_by('-data_pagamento')
        
        dados = []
        for rec in historico:
            data_local = timezone.localtime(rec.data_pagamento)
            dados.append({
                "id": rec.id,
                "data_pagamento": data_local.strftime("%d/%m/%Y %H:%M"),
                "valor_pago": float(rec.valor_pago),
                "referencia_inicio": rec.referencia_inicio.strftime("%d/%m/%Y") if rec.referencia_inicio else "-",
                "referencia_fim": rec.referencia_fim.strftime("%d/%m/%Y") if rec.referencia_fim else "-"
            })
        return Response(dados)