# galeria/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Foto
from .tasks import processar_foto_task # Importa nossa nova tarefa
from .models import Foto, Video # Adicione Video
from .tasks import processar_foto_task, gerar_miniatura_video_task

@receiver(post_save, sender=Foto)
def processar_nova_foto_signal(sender, instance, created, **kwargs):
    """
    Signal que é acionado após uma Foto ser salva.
    Se for uma nova foto, dispara a tarefa Celery para processamento em segundo plano.
    """
    if created:
        print(f"--- Signal disparado para Foto ID: {instance.id}. Enviando para o Celery... ---")
        # .delay() é o que envia a tarefa para a fila para ser executada em segundo plano.
        processar_foto_task.delay(instance.id)
        
@receiver(post_save, sender=Video)
def processar_novo_video_signal(sender, instance, created, **kwargs):
    if created:
        print(f"--- Signal disparado para Vídeo ID: {instance.id}. Enviando para o Celery... ---")
        gerar_miniatura_video_task.delay(instance.id)