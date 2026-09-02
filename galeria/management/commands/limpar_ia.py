import boto3
import time
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
        
        # 🚀 MÁGICA 1: O máximo que a AWS permite de uma vez são 4000 rostos.
        # Ao usar 4000, baixamos as requisições de 67 para apenas 17!
        lotes = [lista_rostos[i:i + 4000] for i in range(0, len(lista_rostos), 4000)]
        
        total_apagados = 0
        for index, lote in enumerate(lotes):
            try:
                response = client.delete_faces(
                    CollectionId=settings.AWS_REKOGNITION_COLLECTION_ID,
                    FaceIds=lote
                )
                apagados_no_lote = len(response.get('DeletedFaces', []))
                total_apagados += apagados_no_lote
                
                # Remove do banco de dados local para manter a sincronia
                FaceIndexada.objects.filter(rekognition_face_id__in=lote).delete()
                
                self.stdout.write(self.style.SUCCESS(f"Lote {index + 1}/{len(lotes)} limpo com sucesso..."))
                
                # 🚀 MÁGICA 2: Descanso maior entre os super-lotes (5 segundos)
                time.sleep(5)
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Erro ao apagar lote na AWS: {str(e)}"))
                # Se ainda assim der erro, descansa mais tempo (10 seg) e avança para o próximo
                time.sleep(10)
            
        self.stdout.write(self.style.SUCCESS(f"🗑️ Missão Cumprida! {total_apagados} rostos antigos foram excluídos permanentemente da AWS."))