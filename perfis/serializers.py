# perfis/serializers.py
from rest_framework import serializers
from .models import PerfilCliente, PerfilFotografo
from contas.models import Usuario

class FotografoPublicoSerializer(serializers.ModelSerializer):
    nome_completo = serializers.CharField(source='usuario.nome_completo')
    foto_perfil_url = serializers.URLField(source='foto_perfil.url', read_only=True)

    class Meta:
        model = PerfilFotografo
        fields = ['id', 'nome_completo', 'foto_perfil_url', 'especialidade', 'rede_social']

class PerfilClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerfilCliente
        fields = ['cpf', 'endereco', 'cep']

class PerfilFotografoSerializer(serializers.ModelSerializer):
    foto_perfil_url = serializers.URLField(source='foto_perfil.url', read_only=True)
    
    class Meta:
        model = PerfilFotografo
        # Adicione os novos campos à lista
        fields = [
            'cpf', 'endereco', 'cep',
            'foto_perfil_url',
            'registro_profissional', 'numero_registro', 'banco', 
            'agencia', 'conta', 'chave_pix'
        ]
