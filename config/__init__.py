# config/__init__.py

# Importa nosso app Celery para garantir que ele seja carregado quando o Django iniciar.
from .celery import app as celery_app

__all__ = ('celery_app',)