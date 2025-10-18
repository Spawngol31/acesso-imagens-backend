# contas/views.py

from django.core.mail import send_mail
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.conf import settings
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from .models import Usuario
from .permissions import IsAdminUser
from .serializers import UsuarioSerializer, UserRegistrationSerializer, UserAdminSerializer

# Esta view já existia
class PerfilUsuarioView(APIView):
    """
    View para obter os dados do usuário logado.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        O método GET é chamado quando uma requisição GET é feita para a URL.
        """
        usuario = request.user
        serializer = UsuarioSerializer(usuario)
        return Response(serializer.data)

# Esta foi a view que adicionámos
class UserRegistrationView(generics.CreateAPIView):
    """
    View para criar um novo utilizador no sistema.
    """
    queryset = Usuario.objects.all()
    # Permite que qualquer pessoa (mesmo não logada) aceda a este endpoint
    permission_classes = (AllowAny,)
    serializer_class = UserRegistrationSerializer

class UserAdminViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.all().order_by('id')
    serializer_class = UserAdminSerializer
    permission_classes = [IsAdminUser] # Apenas Admins podem aceder

    @action(
        detail=True, 
        methods=['post'], 
        parser_classes=[MultiPartParser, FormParser]
    )
    def upload_foto_perfil(self, request, pk=None):
        user = self.get_object()
        
        # Verifica se o utilizador é um fotógrafo
        if not hasattr(user, 'perfil_fotografo'):
            return Response(
                {'error': 'Este utilizador não tem um perfil de fotógrafo.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        file_obj = request.FILES.get('foto_perfil')
        if not file_obj:
            return Response(
                {'error': 'Nenhum ficheiro foi enviado.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Guarda o novo ficheiro
        user.perfil_fotografo.foto_perfil = file_obj
        user.perfil_fotografo.save()
        
        # Retorna os dados atualizados do utilizador
        serializer = self.get_serializer(user)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def bloquear(self, request, pk=None):
        """Ação customizada para bloquear (desativar) um utilizador."""
        user = self.get_object()
        user.is_active = False
        user.save()
        return Response({'status': f'Utilizador {user.email} bloqueado'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def desbloquear(self, request, pk=None):
        """Ação customizada para desbloquear (ativar) um utilizador."""
        user = self.get_object()
        user.is_active = True
        user.save()
        return Response({'status': f'Utilizador {user.email} desbloqueado'}, status=status.HTTP_200_OK)

class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')
        try:
            user = Usuario.objects.get(email=email)
            
            token_generator = PasswordResetTokenGenerator()
            token = token_generator.make_token(user)
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            
            # ATENÇÃO: Use o URL do seu frontend aqui!
            reset_link = f"http://localhost:5173/resetar-senha/{uidb64}/{token}"

            send_mail(
                'Recuperação de Senha - Acesso Imagens',
                f'Olá {user.nome_completo},\n\nClique no link a seguir para redefinir a sua senha:\n{reset_link}\n\nSe não foi você que solicitou, por favor ignore este e-mail.',
                settings.DEFAULT_FROM_EMAIL, # Opcional, pode ser 'nao-responda@acessoimagens.com'
                [user.email],
                fail_silently=False,
            )

        except Usuario.DoesNotExist:
            # Não revela que o e-mail não existe por segurança
            pass

        return Response({'message': 'Se o e-mail estiver registado, um link de recuperação foi enviado.'}, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

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
