# perfis/views.py
from rest_framework import generics
from rest_framework.permissions import AllowAny
from contas.models import Usuario
from .models import PerfilFotografo
from .serializers import FotografoPublicoSerializer

class FotografoListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = FotografoPublicoSerializer
    
    # Substituímos o 'queryset' fixo por uma função dinâmica que 
    # filtra exatamente os membros da equipa que queremos exibir.
    def get_queryset(self):
        papeis_da_equipe = [
            Usuario.Papel.FOTOGRAFO,
            Usuario.Papel.JORNALISTA,
            Usuario.Papel.ASSESSOR_IMPRENSA,
            Usuario.Papel.ASSESSOR_COMUNICACAO,
            Usuario.Papel.VIDEOMAKER,
            Usuario.Papel.CRIADOR_CONTEUDO
        ]
        
        return PerfilFotografo.objects.filter(
            usuario__is_active=True,
            usuario__papel__in=papeis_da_equipe
        )