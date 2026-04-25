# perfis/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from contas.models import Usuario
from .models import PerfilCliente, PerfilFotografo

@receiver(post_save, sender=Usuario)
def criar_ou_atualizar_perfil_usuario(sender, instance, created, **kwargs):
    # Definimos quem tem direito ao Perfil Profissional (PerfilFotografo)
    papeis_da_equipe = [
        Usuario.Papel.FOTOGRAFO,
        Usuario.Papel.JORNALISTA,
        Usuario.Papel.ASSESSOR_IMPRENSA,
        Usuario.Papel.ASSESSOR_COMUNICACAO,
        Usuario.Papel.VIDEOMAKER,
        Usuario.Papel.CRIADOR_CONTEUDO
    ]

    if created:
        if instance.papel == Usuario.Papel.CLIENTE:
            PerfilCliente.objects.get_or_create(usuario=instance)
        elif instance.papel in papeis_da_equipe: # CORREÇÃO AQUI
            PerfilFotografo.objects.get_or_create(usuario=instance)
    else:
        if instance.papel == Usuario.Papel.CLIENTE:
            PerfilCliente.objects.get_or_create(usuario=instance)
            if hasattr(instance, 'perfil_fotografo'):
                instance.perfil_fotografo.delete()
        
        elif instance.papel in papeis_da_equipe: # CORREÇÃO AQUI
            PerfilFotografo.objects.get_or_create(usuario=instance)
            if hasattr(instance, 'perfil_cliente'):
                instance.perfil_cliente.delete()