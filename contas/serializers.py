# contas/serializers.py

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import Usuario
from perfis.serializers import PerfilClienteSerializer, PerfilFotografoSerializer

class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ['id', 'email', 'nome_completo', 'papel']

class UserRegistrationSerializer(serializers.ModelSerializer):
    password2 = serializers.CharField(style={'input_type': 'password'}, write_only=True)

    class Meta:
        model = Usuario
        fields = ['email', 'nome_completo', 'password', 'password2']
        extra_kwargs = { 'password': {'write_only': True} }

    def save(self):
        user = Usuario(
            email=self.validated_data['email'],
            nome_completo=self.validated_data['nome_completo']
        )
        password = self.validated_data['password']
        password2 = self.validated_data['password2']
        if password != password2:
            raise serializers.ValidationError({'password': 'As senhas não coincidem.'})
        user.set_password(password)
        user.save()
        return user

class UserAdminSerializer(serializers.ModelSerializer):
    perfil_cliente = PerfilClienteSerializer(required=False, allow_null=True)
    perfil_fotografo = PerfilFotografoSerializer(required=False, allow_null=True)

    class Meta:
        model = Usuario
        fields = [
            'id', 'email', 'nome_completo', 'papel', 'is_active',
            'perfil_cliente', 'perfil_fotografo'
        ]
    
    def update(self, instance, validated_data):
        # 1. Separa os dados dos perfis
        perfil_cliente_data = validated_data.pop('perfil_cliente', None)
        perfil_fotografo_data = validated_data.pop('perfil_fotografo', None)
        
        # 2. Atualiza o utilizador principal. Se o 'papel' mudar, o signal será acionado.
        instance = super().update(instance, validated_data)

        # 3. Atualiza os perfis DEPOIS de o utilizador ser atualizado.
        #    Usamos 'refresh_from_db' para garantir que temos o objeto mais recente,
        #    especialmente se o signal alterou os perfis.
        instance.refresh_from_db() 
        
        if instance.papel == Usuario.Papel.CLIENTE and perfil_cliente_data and hasattr(instance, 'perfil_cliente'):
            perfil_serializer = PerfilClienteSerializer(instance.perfil_cliente, data=perfil_cliente_data, partial=True)
            perfil_serializer.is_valid(raise_exception=True)
            perfil_serializer.save()

        elif instance.papel == Usuario.Papel.FOTOGRAFO and perfil_fotografo_data and hasattr(instance, 'perfil_fotografo'):
            perfil_serializer = PerfilFotografoSerializer(instance.perfil_fotografo, data=perfil_fotografo_data, partial=True)
            perfil_serializer.is_valid(raise_exception=True)
            perfil_serializer.save()

        return instance
    
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Personaliza o token JWT para incluir o papel do utilizador e o nome.
    O login continua a ser feito pelo USERNAME_FIELD (que definimos como email).
    """
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Adiciona dados personalizados ao token
        token['nome_completo'] = user.nome_completo
        token['papel'] = user.papel

        return token