# contas/views.py

import os
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

# --- CORREÇÃO NAS IMPORTAÇÕES ---
# Importa APENAS os serializers necessários de 'serializers.py'
from .serializers import (
    UsuarioSerializer, 
    UserRegistrationSerializer, 
    UserAdminSerializer,
    CustomTokenObtainPairSerializer
)
from .models import Usuario
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

# --- ViewSet de Admin (COM A CORREÇÃO DO 'username') ---
class UserAdminViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.all().order_by('id')
    serializer_class = UserAdminSerializer
    permission_classes = [IsAdminUser]
    
    filter_backends = [SearchFilter]
    # --- CORREÇÃO AQUI: 'username' removido ---
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

# --- Views de Recuperação de Senha ---
class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get('email')
        
        # --- LÓGICA DE URL DINÂMICA ---
        # Lê a URL do frontend a partir das variáveis de ambiente
        frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
        # ----------------------------

        try:
            user = Usuario.objects.get(email=email)
            token_generator = PasswordResetTokenGenerator()
            token = token_generator.make_token(user)
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            
            # --- CORREÇÃO AQUI ---
            # Usa a nossa variável dinâmica
            reset_link = f"{frontend_url}/resetar-senha/{uidb64}/{token}"

            send_mail(
                'Recuperação de Senha - Acesso Imagens',
                f'Olá {user.nome_completo},\n\nClique no link a seguir para redefinir a sua senha:\n{reset_link}\n\nSe não foi você que solicitou, por favor ignore este e-mail.',
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
        except Usuario.DoesNotExist:
            pass
        return Response({'message': 'Se o e-mail estiver registado, um link de recuperação foi enviado.'}, status=status.HTTP_200_OK)

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