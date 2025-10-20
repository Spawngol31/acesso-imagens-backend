# perfis/serializers.py

from rest_framework import serializers
from .models import PerfilCliente, PerfilFotografo

# Serializer para a página pública "Quem Somos"
class FotografoPublicoSerializer(serializers.ModelSerializer):
    nome_completo = serializers.CharField(source='usuario.nome_completo')
    # --- CORREÇÃO 1: Mudar para SerializerMethodField ---
    foto_perfil_url = serializers.SerializerMethodField()

    class Meta:
        model = PerfilFotografo
        fields = ['id', 'nome_completo', 'foto_perfil_url', 'especialidade', 'rede_social']

    # --- CORREÇÃO 1: Adicionar o método defensivo ---
    def get_foto_perfil_url(self, obj):
        # Verifica se a foto existe antes de pedir a URL
        if obj.foto_perfil and obj.foto_perfil.name:
            return obj.foto_perfil.url
        return None # Retorna nulo se não houver foto, em vez de crashar

# Serializer para o perfil do cliente no painel de admin
class PerfilClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerfilCliente
        fields = ['cpf', 'endereco', 'cep']

# Serializer para o perfil do fotógrafo no painel de admin
class PerfilFotografoSerializer(serializers.ModelSerializer):
    # --- CORREÇÃO 2: Mudar para SerializerMethodField ---
    foto_perfil_url = serializers.SerializerMethodField()
    
    class Meta:
        model = PerfilFotografo
        # --- CORREÇÃO 3: Adicionar os campos em falta ---
        fields = [
            'cpf', 'endereco', 'cep',
            'foto_perfil_url',
            'especialidade', # Adicionado
            'rede_social',   # Adicionado
            'registro_profissional', 'numero_registro', 'banco', 
            'agencia', 'conta', 'chave_pix'
        ]

    # --- CORREÇÃO 2: Adicionar o método defensivo ---
    def get_foto_perfil_url(self, obj):
        if obj.foto_perfil and obj.foto_perfil.name:
            return obj.foto_perfil.url
        return None