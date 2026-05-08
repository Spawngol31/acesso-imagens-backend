# perfis/views.py
from rest_framework import generics
from rest_framework.permissions import AllowAny
from contas.models import Usuario
from .models import PerfilFotografo
from .serializers import FotografoPublicoSerializer

class FotografoListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = FotografoPublicoSerializer
    
    def get_queryset(self):
        papeis_da_equipe = [
            Usuario.Papel.FOTOGRAFO,
            Usuario.Papel.JORNALISTA,
            Usuario.Papel.ASSESSOR_IMPRENSA,
            Usuario.Papel.ASSESSOR_COMUNICACAO,
            Usuario.Papel.VIDEOMAKER,
            Usuario.Papel.CRIADOR_CONTEUDO
        ]
        
        # 🚀 APLICAÇÃO DA BOA PRÁTICA:
        # Filtramos e já pedimos ao Banco de Dados para ordenar pelo ID do usuário
        return PerfilFotografo.objects.filter(
            usuario__is_active=True,
            usuario__papel__in=papeis_da_equipe
        ).order_by('usuario__id') # Ordena do menor ID para o maior (mais antigos primeiro)