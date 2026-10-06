# galeria/admin.py

from django.db.models import Q
from django.contrib import admin, messages
from .models import Album, Foto, Video
from .tasks import apagar_midias_antigas_task

@admin.action(description='Limpar Mídias Não Compradas e Arquivar Álbum')
def limpar_e_arquivar_albuns(modeladmin, request, queryset):
    total_fotos_apagadas = 0
    total_videos_apagados = 0
    albuns_processados = 0

    # O queryset são os Álbuns que você selecionou na tela
    for album in queryset:
        
        # 1. FILTRAR FOTOS: Pega todas as fotos deste álbum, EXCLUINDO as que têm pedidos PAGOS ou CONCLUÍDOS
        fotos_sem_venda = Foto.objects.filter(album=album).exclude(
            Q(itempedido__pedido__status='PAGO') | Q(itempedido__pedido__status='CONCLUIDO')
        ).values_list('id', flat=True)

        # 2. FILTRAR VÍDEOS: Pega todos os vídeos deste álbum que não venderam
        videos_sem_venda = Video.objects.filter(album=album).exclude(
            Q(itempedido__pedido__status='PAGO') | Q(itempedido__pedido__status='CONCLUIDO')
        ).values_list('id', flat=True)

        fotos_ids = list(fotos_sem_venda)
        videos_ids = list(videos_sem_venda)

        total_fotos_apagadas += len(fotos_ids)
        total_videos_apagados += len(videos_ids)

        # 3. MANDA PARA O CELERY: O nosso Celery já sabe destruir tudo de forma segura!
        if fotos_ids or videos_ids:
            apagar_midias_antigas_task.delay(fotos_ids, videos_ids)

        # 4. ARQUIVAR O ÁLBUM
        # ATENÇÃO: Confirme o nome do campo no seu models.py. 
        # Estou a assumir que se chama 'is_arquivado' ou 'ativo'. Ajuste abaixo se necessário.
        if hasattr(album, 'is_arquivado'):
            album.is_arquivado = True
        elif hasattr(album, 'ativo'):
            album.ativo = False
            
        album.save()
        albuns_processados += 1

    messages.success(request, f"Mágica feita! {albuns_processados} álbuns arquivados. O Celery está apagando {total_fotos_apagadas} fotos e {total_videos_apagados} vídeos que não foram vendidos.")

@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'fotografo', 'data_evento', 'criado_em')
    list_filter = ('fotografo', 'data_evento')
    search_fields = ('titulo', 'descricao')
    prepopulated_fields = {'slug': ('titulo',)}
    
    # 🚀 Injeta a nova ação inteligente no painel do álbum
    actions = [limpar_e_arquivar_albuns]


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