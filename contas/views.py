# contas/views.py

import os
import urllib.request
import json
import requests

from django.http import HttpResponse
from django.core.mail import send_mail
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from rest_framework import generics, status, viewsets, authentication
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.filters import SearchFilter
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken

# Importa APENAS os serializers necessários de 'serializers.py'
from .serializers import (
    UsuarioSerializer, 
    UserRegistrationSerializer, 
    UserAdminSerializer,
    CustomTokenObtainPairSerializer
)
from .models import Usuario
from perfis.models import PerfilFotografo
from .permissions import IsAdminUser, IsFotografoOrAdmin

# --- View do Perfil do Utilizador ---
class PerfilUsuarioView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        serializer = UsuarioSerializer(request.user)
        return Response(serializer.data)

# --- View de Registo de Utilizador ---
@method_decorator(csrf_exempt, name='dispatch')
class UserRegistrationView(generics.CreateAPIView):
    queryset = Usuario.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]
    authentication_classes = [] 

# --- ViewSet de Admin ---
class UserAdminViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.all().order_by('id')
    serializer_class = UserAdminSerializer
    permission_classes = [IsAdminUser]
    
    filter_backends = [SearchFilter]
    search_fields = ['nome_completo', 'email']

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_foto_perfil(self, request, pk=None):
        user = self.get_object()
        if not hasattr(user, 'perfil_fotografo'):
            return Response({'error': 'Este utilizador não tem um perfil de fotógrafo.'}, status=status.HTTP_400_BAD_REQUEST)
        file_obj = request.FILES.get('foto_perfil')
        if not file_obj:
            return Response({'error': 'Nenhum ficheiro foi enviado.'}, status=status.HTTP_400_BAD_REQUEST)
        user.perfil_fotografo.foto_perfil = file_obj
        user.perfil_fotografo.save()
        serializer = self.get_serializer(user)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def bloquear(self, request, pk=None):
        user = self.get_object()
        user.is_active = False
        user.save()
        return Response({'status': 'utilizador bloqueado'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def desbloquear(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save()
        return Response({'status': 'utilizador desbloqueado'}, status=status.HTTP_200_OK)


# --- Views de Recuperação de Senha (CORRIGIDAS COM ANTI-CSRF) ---

# APLICÁMOS A VACINA ANTI-CSRF AQUI 👇
@method_decorator(csrf_exempt, name='dispatch')
class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [] # Adicionado para evitar que o DRF force a verificação de tokens nesta rota
    
    def post(self, request):
        email = request.data.get('email')
        
        # Lê a URL do frontend a partir das variáveis de ambiente
        frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')

        try:
            user = Usuario.objects.get(email=email)
            token_generator = PasswordResetTokenGenerator()
            token = token_generator.make_token(user)
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            
            reset_link = f"{frontend_url}/resetar-senha/{uidb64}/{token}"

            send_mail(
                'Recuperação de Senha - Acesso Imagens',
                f'Olá {user.nome_completo},\n\nClique no link a seguir para redefinir a sua senha:\n{reset_link}\n\nSe não foi você que solicitou, por favor ignore este e-mail.',
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
        except Usuario.DoesNotExist:
            # Por segurança, não avisamos o hacker se o e-mail existe ou não.
            pass
            
        return Response({'message': 'Se o e-mail estiver registado, um link de recuperação foi enviado.'}, status=status.HTTP_200_OK)


# APLICÁMOS A VACINA ANTI-CSRF AQUI 👇
@method_decorator(csrf_exempt, name='dispatch')
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    
    def post(self, request):
        uidb64 = request.data.get('uidb64')
        token = request.data.get('token')
        password = request.data.get('password')
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = Usuario.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, Usuario.DoesNotExist):
            user = None
            
        token_generator = PasswordResetTokenGenerator()
        if user is not None and token_generator.check_token(user, token):
            user.set_password(password)
            user.save()
            return Response({'message': 'Senha redefinida com sucesso!'}, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'Link de redefinição inválido ou expirado.'}, status=status.HTTP_400_BAD_REQUEST)
            

class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Usa o nosso serializer personalizado que faz o login com email.
    """
    serializer_class = CustomTokenObtainPairSerializer

# Gera tokens personalizados (com nome e papel)
def get_tokens_for_user_with_claims(user):
    refresh = RefreshToken.for_user(user)
    
    refresh['nome_completo'] = user.nome_completo or user.email
    refresh['papel'] = user.papel or Usuario.Papel.CLIENTE

    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

# --- VIEW DO GOOGLE ---
class GoogleLoginView(APIView):
    authentication_classes = [] 
    permission_classes = [AllowAny] 

    def post(self, request):
        token_google = request.data.get('credential')
        if not token_google:
            return Response({'error': 'Nenhum token foi recebido do React.'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            from google.oauth2 import id_token
            from google.auth.transport import requests as google_requests
            
            idinfo = id_token.verify_oauth2_token(
                token_google, google_requests.Request(), settings.GOOGLE_CLIENT_ID
            )

            email = idinfo['email']
            nome = idinfo.get('name', 'Usuário Google')

            user, created = Usuario.objects.get_or_create(email=email, defaults={
                'nome_completo': nome,
                'papel': Usuario.Papel.CLIENTE,
                'is_active': True
            })

            if created:
                user.set_unusable_password()
                user.save()

            tokens = get_tokens_for_user_with_claims(user)
            
            return Response({
                'refresh': tokens['refresh'],
                'access': tokens['access'],
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'nome_completo': user.nome_completo,
                    'papel': user.papel
                }
            })
            
        except ValueError:
            return Response({'error': 'Autenticação do Google falhou.'}, status=status.HTTP_400_BAD_REQUEST)


# --- VIEW DO FACEBOOK ---
class FacebookLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        token_facebook = request.data.get('accessToken')
        if not token_facebook:
            return Response({'error': 'Nenhum token foi recebido do React.'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            url = f"https://graph.facebook.com/me?fields=id,name,email&access_token={token_facebook}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req) as response:
                resposta = json.loads(response.read().decode())

            if 'error' in resposta:
                return Response({'error': 'Token do Facebook inválido ou expirado.'}, status=status.HTTP_400_BAD_REQUEST)

            email = resposta.get('email')
            nome = resposta.get('name', 'Usuário Facebook')

            if not email:
                return Response({'error': 'Precisamos da permissão de e-mail no Facebook.'}, status=status.HTTP_400_BAD_REQUEST)

            user, created = Usuario.objects.get_or_create(email=email, defaults={
                'nome_completo': nome,
                'papel': Usuario.Papel.CLIENTE,
                'is_active': True
            })

            if created:
                user.set_unusable_password()
                user.save()

            tokens = get_tokens_for_user_with_claims(user)
            
            return Response({
                'refresh': tokens['refresh'],
                'access': tokens['access'],
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'nome_completo': user.nome_completo,
                    'papel': user.papel
                }
            })
            
        except Exception as e:
            print("ERRO NO LOGIN DO FACEBOOK:", str(e))
            return Response({'error': f'Erro interno no servidor: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
@method_decorator(csrf_exempt, name='dispatch')
class ImageProxyView(APIView):
    """
    Ponte segura que busca a imagem na AWS e entrega ao React,
    eliminando erros de CORS no localhost e produção.
    """
    permission_classes = [AllowAny] # Aberto para o React usar no painel
    authentication_classes = [] 

    def get(self, request):
        image_url = request.GET.get('url')
        
        if not image_url:
            return Response({'error': 'A URL da imagem é obrigatória.'}, status=status.HTTP_400_BAD_REQUEST)

        # Seguranca: Garante que só buscamos imagens do SEU bucket da Amazon
        if 'amazonaws.com' not in image_url:
             return Response({'error': 'URL inválida.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # O Django faz o download da imagem (sem bloqueio de CORS)
            response = requests.get(image_url, stream=True)
            
            if response.status_code == 200:
                # Prepara a resposta para o React com o tipo de ficheiro correto
                django_response = HttpResponse(response.content, content_type=response.headers['Content-Type'])
                # Autoriza o React a ler esta resposta (CORS livre)
                django_response["Access-Control-Allow-Origin"] = "*" 
                return django_response
            else:
                return Response({'error': 'Não foi possível buscar a imagem na AWS.'}, status=response.status_code)
                
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class MeuPerfilView(APIView):
    permission_classes = [IsAuthenticated]

    # Lista de papéis que dão direito ao painel profissional
    PAPEIS_EQUIPE = [
        Usuario.Papel.FOTOGRAFO, Usuario.Papel.JORNALISTA, Usuario.Papel.ASSESSOR_IMPRENSA,
        Usuario.Papel.ASSESSOR_COMUNICACAO, Usuario.Papel.VIDEOMAKER, Usuario.Papel.CRIADOR_CONTEUDO
    ]

    def get(self, request):
        user = request.user
        
        # Dados básicos (Tabela Usuario)
        dados = {
            "nome_completo": user.nome_completo,
            "email": user.email,
            "papel": user.papel,
        }
        
        # Dados profissionais (Tabela PerfilFotografo)
        if user.papel in self.PAPEIS_EQUIPE:
            try:
                perfil = PerfilFotografo.objects.get(usuario=user)
                dados.update({
                    "cpf": getattr(perfil, 'cpf', ''),
                    "endereco": getattr(perfil, 'endereco', ''),
                    "cep": getattr(perfil, 'cep', ''),
                    "rede_social": getattr(perfil, 'rede_social', ''),
                    "registro_profissional": getattr(perfil, 'registro_profissional', ''),
                    "numero_registro": getattr(perfil, 'numero_registro', ''),
                    "banco": getattr(perfil, 'banco', ''),
                    "agencia": getattr(perfil, 'agencia', ''),
                    "conta": getattr(perfil, 'conta', ''),
                    "chave_pix": getattr(perfil, 'chave_pix', ''),
                })
            except PerfilFotografo.DoesNotExist:
                pass
            
        return Response(dados)

    def patch(self, request):
        user = request.user
        data = request.data
        
        # 1. Atualiza a Tabela Usuario (Nome e Senha)
        if 'nome_completo' in data: 
            user.nome_completo = data['nome_completo']
            
        if 'nova_senha' in data and data['nova_senha']: 
            user.set_password(data['nova_senha'])

        user.save()

        # 2. Atualiza a Tabela PerfilFotografo (Apenas se pertencer à equipa)
        if user.papel in self.PAPEIS_EQUIPE:
            perfil, created = PerfilFotografo.objects.get_or_create(usuario=user)
            
            # Repare que "foto_perfil" e "especialidade" NÃO ESTÃO AQUI. 
            # O Django vai simplesmente ignorá-los se o fotógrafo tentar enviá-los,
            # blindando o sistema para que só o Admin possa mexer nisso!
            if 'cpf' in data: perfil.cpf = data['cpf']
            if 'endereco' in data: perfil.endereco = data['endereco']
            if 'cep' in data: perfil.cep = data['cep']
            if 'rede_social' in data: perfil.rede_social = data['rede_social']
            if 'registro_profissional' in data: perfil.registro_profissional = data['registro_profissional']
            if 'numero_registro' in data: perfil.numero_registro = data['numero_registro']
            if 'banco' in data: perfil.banco = data['banco']
            if 'agencia' in data: perfil.agencia = data['agencia']
            if 'conta' in data: perfil.conta = data['conta']
            if 'chave_pix' in data: perfil.chave_pix = data['chave_pix']
            
            perfil.save()

        return Response({"mensagem": "Perfil atualizado com sucesso!"}, status=status.HTTP_200_OK)