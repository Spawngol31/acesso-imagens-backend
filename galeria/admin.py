# galeria/admin.py
from django.contrib import admin
from .models import Album, Foto, Video # 1. Importe o Video aqui

@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'fotografo', 'data_evento', 'criado_em')
    list_filter = ('fotografo', 'data_evento')
    search_fields = ('titulo', 'descricao')
    prepopulated_fields = {'slug': ('titulo',)} # Adiciona um helper para o slug

@admin.register(Foto)
class FotoAdmin(admin.ModelAdmin):
    list_display = ('id', 'album', 'preco', 'data_upload')
    list_filter = ('album',)
    search_fields = ('legenda',)

# --- 2. ADICIONE ESTE NOVO BLOCO ---
@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ('id', 'titulo', 'album', 'preco', 'data_upload')
    list_filter = ('album',)
    search_fields = ('titulo',)