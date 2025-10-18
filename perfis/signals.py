# perfis/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from contas.models import Usuario
from .models import PerfilCliente, PerfilFotografo

@receiver(post_save, sender=Usuario)
def criar_ou_atualizar_perfil_usuario(sender, instance, created, **kwargs):
    if created:
        # Se for um novo utilizador, cria o perfil apropriado
        if instance.papel == Usuario.Papel.CLIENTE:
            PerfilCliente.objects.get_or_create(usuario=instance)
        elif instance.papel == Usuario.Papel.FOTOGRAFO:
            PerfilFotografo.objects.get_or_create(usuario=instance)
    else:
        # Se for uma atualização, verifica se o perfil correspondente existe e cria-o se não existir.
        # Isto lida com a mudança de papel pelo administrador.
        if instance.papel == Usuario.Papel.CLIENTE:
            PerfilCliente.objects.get_or_create(usuario=instance)
            # Opcional: Apagar o perfil de fotógrafo antigo se existir
            if hasattr(instance, 'perfil_fotografo'):
                instance.perfil_fotografo.delete()
        
        elif instance.papel == Usuario.Papel.FOTOGRAFO:
            PerfilFotografo.objects.get_or_create(usuario=instance)
            # Opcional: Apagar o perfil de cliente antigo se existir
            if hasattr(instance, 'perfil_cliente'):
                instance.perfil_cliente.delete()