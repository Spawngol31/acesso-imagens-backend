# Crie o ficheiro perfis/views.py e adicione:
from rest_framework import generics
from rest_framework.permissions import AllowAny
from contas.models import Usuario
from .models import PerfilFotografo
from .serializers import FotografoPublicoSerializer

class FotografoListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = FotografoPublicoSerializer
    queryset = PerfilFotografo.objects.filter(usuario__is_active=True)