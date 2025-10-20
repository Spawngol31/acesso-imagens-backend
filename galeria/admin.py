# galeria/admin.py

from django.contrib import admin
from .models import Album, Foto, Video

@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'fotografo', 'data_evento', 'criado_em')
    list_filter = ('fotografo', 'data_evento')
    search_fields = ('titulo', 'descricao')
    prepopulated_fields = {'slug': ('titulo',)}

@admin.register(Foto)
class FotoAdmin(admin.ModelAdmin):
    # --- CORREÇÃO AQUI ---
    # Removido o 'criado_em' que estava a causar o erro
    list_display = ('id', 'album', 'preco', 'data_upload') 
    list_filter = ('album',)
    search_fields = ('legenda',)

@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    # --- CORREÇÃO AQUI ---
    # Removido o 'criado_em' que estava a causar o erro
    list_display = ('id', 'titulo', 'album', 'preco', 'data_upload')
    list_filter = ('album',)
    search_fields = ('titulo',)