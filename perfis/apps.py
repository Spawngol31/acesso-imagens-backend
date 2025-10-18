from django.apps import AppConfig


class PerfisConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'perfis'

    def ready(self):
        import perfis.signals # Importa os nossos signals