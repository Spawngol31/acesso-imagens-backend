from django.test import TestCase

# contas/tests.py

from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from .models import Usuario

class ContasAPITestCase(APITestCase):
    """
    Suite de testes para a API do app de Contas.
    """

    def setUp(self):
        """
        Este método é executado antes de cada teste.
        É o lugar perfeito para criar objetos que serão usados em múltiplos testes.
        """
        self.user_data = {
            'username': 'testuser',
            'nome_completo': 'Test User',
            'email': 'test@example.com',
            'password': 'strongpassword123'
        }
        self.user = Usuario.objects.create_user(**self.user_data)
    
    def test_acesso_perfil_sem_autenticacao(self):
        """
        Garante que um usuário não autenticado não pode acessar o endpoint de perfil.
        """
        # A função 'reverse' busca a URL pelo nome que demos no urls.py
        url = reverse('perfil_usuario') 
        
        # self.client é um 'Insomnia' embutido para testes.
        # Fazemos uma requisição GET para a URL.
        response = self.client.get(url)
        
        # Verificamos se a resposta foi '401 Unauthorized', como esperado.
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_acesso_perfil_com_autenticacao(self):
        """
        Garante que um usuário autenticado PODE acessar o endpoint de perfil.
        """
        url = reverse('perfil_usuario')
        
        # A 'mágica' do DRF: autentica o cliente para as próximas requisições
        # sem precisar fazer o fluxo de login e token manualmente.
        self.client.force_authenticate(user=self.user)
        
        # Fazemos a requisição, agora autenticados.
        response = self.client.get(url)

        # Verificamos se a resposta foi '200 OK'.
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Verificamos se o email retornado na resposta é o do nosso usuário.
        self.assertEqual(response.data['email'], self.user.email)
        self.assertEqual(response.data['nome_completo'], self.user.nome_completo)
