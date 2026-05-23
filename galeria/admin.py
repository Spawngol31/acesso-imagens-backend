# galeria/admin.py

from django.contrib import admin
from django.contrib import messages
from .models import Album, Foto, Video

@admin.action(description='🧹 Limpar S3: Apagar apenas fotos NÃO VENDIDAS deste álbum')
def limpar_fotos_nao_vendidas(modeladmin, request, queryset):
    total_apagadas = 0

    for album in queryset:
        # Busca todas as fotos do álbum que NÃO possuem nenhum item de pedido vinculado.
        # Isso garante que fotos compradas ou presentes em faturas permaneçam intactas.
        fotos_sem_venda = Foto.objects.filter(album=album, itempedido__isnull=True)

        for foto in fotos_sem_venda:
            try:
                # 1. Deleta o arquivo original (pesado) diretamente do S3
                if foto.imagem:
                    foto.imagem.delete(save=False)
                
                # 2. Deleta a miniatura com marca d'água do S3
                if foto.miniatura_marca_dagua:
                    foto.miniatura_marca_dagua.delete(save=False)
                
                # 3. Elimina o registro correspondente no banco de dados
                foto.delete()
                total_apagadas += 1
            except Exception as e:
                modeladmin.message_user(
                    request,
                    f"Erro ao deletar a foto ID {foto.id}: {str(e)}",
                    messages.ERROR
                )

    if total_apagadas > 0:
        modeladmin.message_user(
            request, 
            f"Limpeza concluída com sucesso! Foram eliminadas {total_apagadas} fotos não vendidas diretamente do S3 e da base de dados.", 
            messages.SUCCESS
        )
    else:
        modeladmin.message_user(
            request,
            "Nenhuma foto pôde ser apagada. Todas as fotos deste álbum possuem vendas vinculadas ou o álbum está vazio.",
            messages.WARNING
        )


@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'fotografo', 'data_evento', 'criado_em')
    list_filter = ('fotografo', 'data_evento')
    search_fields = ('titulo', 'descricao')
    prepopulated_fields = {'slug': ('titulo',)}
    
    # 🚀 Injeta a nova ação inteligente no painel do álbum
    actions = [limpar_fotos_nao_vendidas]


@admin.register(Foto)
class FotoAdmin(admin.ModelAdmin):
    list_display = ('id', 'album', 'preco', 'data_upload') 
    list_filter = ('album',)
    search_fields = ('legenda',)


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ('id', 'titulo', 'album', 'preco', 'data_upload')
    list_filter = ('album',)
    search_fields = ('titulo',)