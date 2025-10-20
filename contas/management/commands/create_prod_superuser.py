# contas/management/commands/create_prod_superuser.py
import os
from django.core.management.base import BaseCommand
from contas.models import Usuario

class Command(BaseCommand):
    help = 'Cria um superusuário para produção de forma não-interativa, lendo de variáveis de ambiente.'

    def handle(self, *args, **options):
        # Email é o novo "username"
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
        nome_completo = os.environ.get('DJANGO_SUPERUSER_NOME_COMPLETO')

        # Verifica se os campos obrigatórios (USERNAME_FIELD + REQUIRED_FIELDS) estão presentes
        if not all([email, password, nome_completo]):
            self.stdout.write(self.style.ERROR('Variáveis de ambiente (DJANGO_SUPERUSER_EMAIL, DJANGO_SUPERUSER_PASSWORD, DJANGO_SUPERUSER_NOME_COMPLETO) não estão definidas.'))
            return

        # --- CORREÇÃO AQUI ---
        # Filtra por 'email' (o nosso USERNAME_FIELD), não por 'username'
        if not Usuario.objects.filter(email=email).exists():
            Usuario.objects.create_superuser(
                email=email,
                password=password,
                nome_completo=nome_completo,
                papel='ADMIN' # Garante que o papel é de Admin
            )
            self.stdout.write(self.style.SUCCESS(f'Superusuário com email "{email}" criado com sucesso.'))
        else:
            self.stdout.write(self.style.WARNING(f'Superusuário com email "{email}" já existe.'))