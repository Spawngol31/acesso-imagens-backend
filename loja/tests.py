from django.test import TestCase

# loja/tests.py

from unittest.mock import patch
from io import BytesIO
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from contas.models import Usuario
from galeria.models import Album, Foto
from .models import Carrinho, ItemCarrinho, Pedido, FotoComprada

def create_dummy_image():
    """Cria um arquivo de imagem JPEG de 1x1 pixel em memória."""
    f = BytesIO()
    image = Image.new('RGB', (100, 100))
    image.save(f, 'jpeg')
    f.seek(0)
    return SimpleUploadedFile('test.jpg', f.read(), content_type='image/jpeg')

@override_settings(DEFAULT_FILE_STORAGE='django.core.files.storage.FileSystemStorage')
class LojaAPITestCase(APITestCase):
    
    def setUp(self):
        """
        Configura um ambiente rico para os testes com múltiplos usuários e objetos.
        """
        self.fotografo = Usuario.objects.create_user(
            username='fotografo_loja', email='fotografo_loja@example.com', password='password', papel=Usuario.Papel.FOTOGRAFO
        )
        self.cliente1 = Usuario.objects.create_user(
            username='cliente1', email='cliente1@example.com', password='password', papel=Usuario.Papel.CLIENTE
        )
        self.cliente2 = Usuario.objects.create_user(
            username='cliente2', email='cliente2@example.com', password='password', papel=Usuario.Papel.CLIENTE
        )
        
        self.album = Album.objects.create(titulo="Álbum de Teste Loja", data_evento="2025-01-01", fotografo=self.fotografo)
        self.foto1 = Foto.objects.create(album=self.album, preco=15.00, imagem=create_dummy_image())
        self.foto2 = Foto.objects.create(album=self.album, preco=20.00, imagem=create_dummy_image())

    # --- Testes do Carrinho de Compras ---

    def test_cliente_pode_adicionar_item_ao_carrinho(self):
        """Garante que um cliente logado pode adicionar uma foto ao seu carrinho."""
        url = reverse('carrinho')
        self.client.force_authenticate(user=self.cliente1)
        
        response = self.client.post(url, {'foto_id': self.foto1.id})
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ItemCarrinho.objects.count(), 1)
        self.assertEqual(response.data['itens'][0]['foto']['id'], self.foto1.id)

    def test_adicionar_mesmo_item_nao_duplica(self):
        """Garante que adicionar a mesma foto duas vezes não cria um novo item no carrinho."""
        url = reverse('carrinho')
        self.client.force_authenticate(user=self.cliente1)
        
        self.client.post(url, {'foto_id': self.foto1.id}) # Primeira adição
        self.assertEqual(ItemCarrinho.objects.count(), 1)
        
        response = self.client.post(url, {'foto_id': self.foto1.id}) # Segunda adição
        self.assertEqual(response.status_code, status.HTTP_200_OK) # Deve retornar 200 OK, não 201
        self.assertEqual(ItemCarrinho.objects.count(), 1) # A contagem deve permanecer 1

    def test_cliente_pode_ver_seu_carrinho(self):
        """Garante que um cliente pode ver os detalhes do seu próprio carrinho."""
        url = reverse('carrinho')
        self.client.force_authenticate(user=self.cliente1)
        
        # Adiciona um item para o teste não ser trivial
        ItemCarrinho.objects.create(carrinho=Carrinho.objects.create(cliente=self.cliente1), foto=self.foto1)
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['itens']), 1)
        self.assertEqual(float(response.data['total']), float(self.foto1.preco)) # Compara o total

    def test_cliente_pode_remover_item_do_carrinho(self):
        """Garante que um cliente pode deletar um item do seu carrinho."""
        url = reverse('carrinho')
        carrinho = Carrinho.objects.create(cliente=self.cliente1)
        item = ItemCarrinho.objects.create(carrinho=carrinho, foto=self.foto1)
        
        self.client.force_authenticate(user=self.cliente1)
        response = self.client.delete(url, {'item_id': item.id})
        
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ItemCarrinho.objects.filter(id=item.id).exists())

    # --- Testes de Segurança e Permissão do Carrinho ---

    def test_fotografo_nao_pode_acessar_carrinho(self):
        """Garante que um usuário não-cliente (fotógrafo) não pode acessar a API do carrinho."""
        url = reverse('carrinho')
        self.client.force_authenticate(user=self.fotografo)
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        response = self.client.post(url, {'foto_id': self.foto1.id})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cliente_nao_pode_ver_carrinho_de_outro_cliente(self):
        """TESTE CRÍTICO: Garante isolamento de dados entre clientes."""
        # Cliente 2 cria um item em seu carrinho
        carrinho_cliente2 = Carrinho.objects.create(cliente=self.cliente2)
        ItemCarrinho.objects.create(carrinho=carrinho_cliente2, foto=self.foto1)
        
        # Cliente 1 tenta ver seu próprio carrinho (que está vazio)
        url = reverse('carrinho')
        self.client.force_authenticate(user=self.cliente1)
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['itens']), 0) # Deve ver 0 itens, não o item do cliente 2

    # --- Testes de Pós-Compra ---
    
    def setUp_pos_compra(self):
        """Helper para criar um estado de 'pós-compra' para os testes."""
        self.pedido_pago = Pedido.objects.create(
            cliente=self.cliente1, valor_total=self.foto1.preco, status=Pedido.StatusPedido.PAGO
        )
        self.foto_comprada = FotoComprada.objects.create(cliente=self.cliente1, foto=self.foto1)
        
    def test_cliente_pode_ver_historico_de_compras(self):
        """Garante que o cliente pode listar seus pedidos pagos."""
        self.setUp_pos_compra()
        url = reverse('minhas-compras')
        self.client.force_authenticate(user=self.cliente1)
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.pedido_pago.id)

    def test_cliente_pode_baixar_foto_comprada(self):
        """
        Garante que um cliente pode obter uma URL assinada para uma foto que ele comprou.
        Usamos 'patch' para simular a chamada ao S3, evitando uma chamada de rede real.
        """
        self.setUp_pos_compra()
        url = reverse('download-foto', kwargs={'foto_id': self.foto_comprada.foto.id})
        self.client.force_authenticate(user=self.cliente1)

        # 'patch' substitui a função 'generate_presigned_url' por uma que retorna um valor fixo
        with patch('boto3.client') as mock_s3_client:
            mock_s3_client.return_value.generate_presigned_url.return_value = "http://mocked.s3.url/download"
            response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['download_url'], "http://mocked.s3.url/download")

    def test_cliente_nao_pode_baixar_foto_nao_comprada(self):
        """Garante que um cliente não pode baixar uma foto que não comprou."""
        url = reverse('download-foto', kwargs={'foto_id': self.foto2.id}) # foto2 não foi comprada
        self.client.force_authenticate(user=self.cliente1)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
