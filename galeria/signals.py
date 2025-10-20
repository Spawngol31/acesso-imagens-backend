# galeria/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver

# --- 1. Importações Corrigidas e Consolidadas ---
from .models import Foto, Video
from .tasks import processar_foto_task, gerar_miniatura_video_task

@receiver(post_save, sender=Foto)
def processar_nova_foto_signal(sender, instance, created, **kwargs):
    """
    Signal que é acionado após uma Foto ser salva.
    Se for uma nova foto E ela tiver um ficheiro de imagem,
    dispara a tarefa Celery para processamento.
    """
    # --- 2. Lógica de Verificação Melhorada ---
    if created and instance.imagem:
        print(f"--- Signal disparado para Foto ID: {instance.id}. Enviando para o Celery... ---")
        processar_foto_task.delay(instance.id)
        
@receiver(post_save, sender=Video)
def processar_novo_video_signal(sender, instance, created, **kwargs):
    """
    Signal que é acionado após um Vídeo ser salvo.
    """
    # --- 2. Lógica de Verificação Melhorada ---
    if created and instance.arquivo_video:
        print(f"--- Signal disparado para Vídeo ID: {instance.id}. Enviando para o Celery... ---")
        gerar_miniatura_video_task.delay(instance.id)