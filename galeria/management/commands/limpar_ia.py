import boto3
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from galeria.models import Foto, FaceIndexada

class Command(BaseCommand):
    help = 'Exclui faces da AWS Rekognition de fotos mais antigas que 60 dias'

    def handle(self, *args, **kwargs):
        # 1. Determina a linha de corte: 60 dias atrás (2 meses)
        data_limite = timezone.now() - timedelta(days=60)
        
        # 2. Encontra fotos antigas e pega os IDs das faces atreladas a elas
        fotos_antigas = Foto.objects.filter(data_upload__lt=data_limite)
        faces_para_apagar = FaceIndexada.objects.filter(foto__in=fotos_antigas).values_list('rekognition_face_id', flat=True)
        
        lista_rostos = list(faces_para_apagar)
        
        if not lista_rostos:
            self.stdout.write(self.style.SUCCESS("✨ O cofre da IA está otimizado. Nenhum rosto com mais de 60 dias foi encontrado."))
            return

        client = boto3.client('rekognition', region_name=settings.AWS_REKOGNITION_REGION_NAME)
        
        # 3. A AWS tem um limite de 4000 apagos por vez. Dividimos a lista em lotes de 1000.
        lotes = [lista_rostos[i:i + 1000] for i in range(0, len(lista_rostos), 1000)]
        
        total_apagados = 0
        for lote in lotes:
            try:
                response = client.delete_faces(
                    CollectionId=settings.AWS_REKOGNITION_COLLECTION_ID,
                    FaceIds=lote
                )
                apagados_no_lote = len(response.get('DeletedFaces', []))
                total_apagados += apagados_no_lote
                
                # 4. Remove do banco de dados local para manter a sincronia
                FaceIndexada.objects.filter(rekognition_face_id__in=lote).delete()
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Erro ao apagar lote na AWS: {str(e)}"))
            
        self.stdout.write(self.style.SUCCESS(f"Missão Cumprida! {total_apagados} rostos antigos foram excluídos permanentemente da AWS. (Isso reduzirá sua próxima fatura!)"))