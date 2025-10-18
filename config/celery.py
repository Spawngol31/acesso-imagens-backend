# config/celery.py
import os
from celery import Celery

# Define a variável de ambiente para que o Celery saiba onde encontrar as configurações do Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Cria a instância do Celery
app = Celery('config')

# Carrega as configurações do Celery a partir do settings.py do Django
app.config_from_object('django.conf:settings', namespace='CELERY')

# Descobre e carrega automaticamente as tarefas dos apps Django instalados
app.autodiscover_tasks()