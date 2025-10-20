# galeria/apps.py

from django.apps import AppConfig

# --- CORREÇÃO AQUI ---
class GaleriaConfig(AppConfig): # Corrigido de AppAppConfig para AppConfig
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'galeria'

    def ready(self):
        # Importa os signals para que eles sejam registados
        import galeria.signals