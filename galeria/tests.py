from django.test import TestCase

# galeria/tests.py

from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from django.test import override_settings
from contas.models import Usuario
from .models import Album, Foto
from io import BytesIO
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile

def create_dummy_image():
    f = BytesIO()
    image = Image.new('RGB', (100, 100))
    image.save(f, 'jpeg')
    f.seek(0)
    return SimpleUploadedFile('test.jpg', f.read(), content_type='image/jpeg')

@override_settings(DEFAULT_FILE_STORAGE='django.core.files.storage.FileSystemStorage')
class GaleriaAPITestCase(APITestCase):
    
    def setUp(self):
        """
        Configura o ambiente para cada teste, criando dois fotógrafos
        e um cliente.
        """
        # --- Usuários ---
        self.fotografo1 = Usuario.objects.create_user(
            username='fotografo1',
            nome_completo='Fotógrafo Um',
            email='fotografo1@example.com',
            password='password123',
            papel=Usuario.Papel.FOTOGRAFO
        )
        self.fotografo2 = Usuario.objects.create_user(
            username='fotografo2',
            nome_completo='Fotógrafo Dois',
            email='fotografo2@example.com',
            password='password123',
            papel=Usuario.Papel.FOTOGRAFO
        )
        self.cliente_user = Usuario.objects.create_user(
            username='cliente',
            nome_completo='Cliente Teste',
            email='cliente@example.com',
            password='password123',
            papel=Usuario.Papel.CLIENTE
        )

        # --- Álbuns ---
        # Criamos um álbum que pertence APENAS ao fotografo1
        self.album_fotografo1 = Album.objects.create(
            titulo="Álbum do Fotógrafo 1",
            data_evento="2025-10-10",
            fotografo=self.fotografo1
        )

        self.foto_do_album1 = Foto.objects.create(album=self.album_fotografo1, imagem=create_dummy_image())
    # --- Testes de Permissão ---

    def test_cliente_nao_pode_listar_dashboard_albuns(self):
        """
        Garante que um cliente não pode acessar a lista de álbuns do dashboard.
        """
        url = reverse('dashboard-album-list') # O '-list' é adicionado pelo router
        self.client.force_authenticate(user=self.cliente_user)
        
        response = self.client.get(url)
        
        # Esperamos '403 Forbidden', pois o usuário está logado, mas não tem a permissão (não é fotógrafo)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_fotografo_so_lista_seus_proprios_albuns(self):
        """
        TESTE CRÍTICO: Garante que um fotógrafo logado só vê seus próprios álbuns.
        """
        url = reverse('dashboard-album-list')
        
        # Autenticamos como FOTÓGRAFO 1
        self.client.force_authenticate(user=self.fotografo1)
        response_f1 = self.client.get(url)
        
        # Verificamos se ele vê 1 álbum e se é o álbum correto.
        self.assertEqual(response_f1.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_f1.data), 1)
        self.assertEqual(response_f1.data[0]['titulo'], self.album_fotografo1.titulo)
        
        # Agora, autenticamos como FOTÓGRAFO 2
        self.client.force_authenticate(user=self.fotografo2)
        response_f2 = self.client.get(url)
        
        # Verificamos se a lista de álbuns para ele está VAZIA.
        self.assertEqual(response_f2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_f2.data), 0)

    def test_fotografo_nao_pode_editar_album_de_outro(self):
        """
        TESTE CRÍTICO: Garante que um fotógrafo não pode editar o álbum de outro.
        """
        # O '-detail' é adicionado pelo router para URLs com ID
        url = reverse('dashboard-album-detail', kwargs={'pk': self.album_fotografo1.pk})
        
        # Autenticamos como FOTÓGRAFO 2, tentando editar o álbum do FOTÓGRAFO 1
        self.client.force_authenticate(user=self.fotografo2)
        
        data_update = {'titulo': 'Título Hackeado'}
        response = self.client.patch(url, data_update)
        
        # A API deve retornar '404 Not Found', pois, para o fotógrafo 2, este álbum "não existe".
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        
        # Verificamos no banco de dados se o título do álbum NÃO mudou.
        self.album_fotografo1.refresh_from_db()
        self.assertNotEqual(self.album_fotografo1.titulo, data_update['titulo'])

    # --- Teste de Funcionalidade ---
    
    def test_fotografo_pode_criar_um_album(self):
        """
        Garante que um fotógrafo logado pode criar um novo álbum.
        """
        url = reverse('dashboard-album-list')
        self.client.force_authenticate(user=self.fotografo1)
        
        album_data = {
            'titulo': 'Meu Novo Álbum',
            'data_evento': '2025-11-15',
            'categoria': Album.Categoria.FUTEBOL
        }
        
        response = self.client.post(url, album_data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Verifica se o novo álbum foi associado corretamente ao fotógrafo logado.
        self.assertEqual(response.data['fotografo'], self.fotografo1.id)
        # Verifica se o álbum agora existe no banco de dados.
        self.assertTrue(Album.objects.filter(titulo='Meu Novo Álbum').exists())
