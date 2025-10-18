# perfis/admin.py
from django.contrib import admin
from .models import PerfilCliente, PerfilFotografo

admin.site.register(PerfilCliente)
admin.site.register(PerfilFotografo)