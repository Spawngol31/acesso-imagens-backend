# contas/management/commands/create_prod_superuser.py
import os
from django.core.management.base import BaseCommand
from contas.models import Usuario

class Command(BaseCommand):
    help = 'Cria um superusuário para produção de forma não-interativa, lendo de variáveis de ambiente.'

    def handle(self, *args, **options):
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME')
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
        nome_completo = os.environ.get('DJANGO_SUPERUSER_NOME_COMPLETO')

        if not all([username, email, password, nome_completo]):
            self.stdout.write(self.style.ERROR('Variáveis de ambiente (USERNAME, EMAIL, PASSWORD, NOME_COMPLETO) não estão definidas.'))
            return

        if not Usuario.objects.filter(username=username).exists():
            Usuario.objects.create_superuser(
                username=username,
                email=email,
                password=password,
                nome_completo=nome_completo,
                papel='ADMIN' # Garante que o papel é de Admin
            )
            self.stdout.write(self.style.SUCCESS(f'Superusuário "{username}" criado com sucesso.'))
        else:
            self.stdout.write(self.style.WARNING(f'Superusuário "{username}" já existe.'))