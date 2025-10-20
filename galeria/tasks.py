# galeria/tasks.py
import os
import boto3
import ffmpeg
import tempfile
from io import BytesIO
from PIL import Image, ImageOps

from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from .models import Foto, FaceIndexada, Video # 'Album' foi removido desta linha

@shared_task
def processar_foto_task(foto_id):
    """
    Versão final e robusta da tarefa de processamento de fotos.
    """
    try:
        foto = Foto.objects.get(id=foto_id)
        if not foto.imagem:
            return

        print(f"--- [CELERY] Iniciando processamento para Foto ID: {foto.id} ---")

        with foto.imagem.open('rb') as image_file:
            image_bytes = image_file.read()
        
        # --- LÓGICA DE REDIMENSIONAMENTO PARA O REKOGNITION ---
        REKOGNITION_LIMIT = 5 * 1024 * 1024 # 5MB
        
        if len(image_bytes) > REKOGNITION_LIMIT:
            print(f"--- [CELERY] Imagem > 5MB. Redimensionando para análise... ---")
            img = Image.open(BytesIO(image_bytes))
            img.thumbnail((1920, 1080), Image.Resampling.LANCZOS)
            
            buffer_rekognition = BytesIO()
            img.save(buffer_rekognition, format='JPEG', quality=95)
            image_bytes_for_rekognition = buffer_rekognition.getvalue()
            print(f"--- [CELERY] Imagem redimensionada para {len(image_bytes_for_rekognition)} bytes. ---")
        else:
            image_bytes_for_rekognition = image_bytes

        # --- LÓGICA DE INDEXAÇÃO FACIAL ---
        if not foto.faces_indexadas.exists():
            print(f"--- [CELERY] Iniciando indexação facial... ---")
            rekognition_client = boto3.client('rekognition', region_name=settings.AWS_REKOGNITION_REGION_NAME)
            response = rekognition_client.index_faces(
                CollectionId=settings.AWS_REKOGNITION_COLLECTION_ID,
                Image={'Bytes': image_bytes_for_rekognition},
                ExternalImageId=str(foto.id),
                DetectionAttributes=['DEFAULT']
            )
            novas_faces = []
            for face_record in response.get('FaceRecords', []):
                face_id = face_record['Face']['FaceId']
                novas_faces.append(FaceIndexada(foto=foto, rekognition_face_id=face_id))
            if novas_faces:
                FaceIndexada.objects.bulk_create(novas_faces)
                print(f"--- [CELERY] {len(novas_faces)} faces indexadas com sucesso para a Foto ID: {foto.id} ---")

        # --- LÓGICA DE GERAÇÃO DE MINIATURA ---
        if not foto.miniatura_marca_dagua:
            print(f"--- [CELERY] Gerando miniatura com marca d'água... ---")
            original_image = Image.open(BytesIO(image_bytes)).convert("RGBA")
            
            size = (1024, 1024)
            original_image.thumbnail(size)
            img_width, img_height = original_image.size

            watermark_path = os.path.join(settings.BASE_DIR, 'assets', 'watermark.png')
            watermark = Image.open(watermark_path).convert("RGBA")
            
            PROPORCAO_MARCA = 0.20
            new_wm_width = int(img_width * PROPORCAO_MARCA)
            wm_ratio = new_wm_width / watermark.size[0]
            new_wm_height = int(wm_ratio * watermark.size[1])
            watermark = watermark.resize((new_wm_width, new_wm_height), Image.Resampling.LANCZOS)
            wm_width, wm_height = watermark.size
            
            OPACIDADE = 0.3
            alpha = watermark.getchannel('A')
            alpha = alpha.point(lambda i: i * OPACIDADE)
            watermark.putalpha(alpha)

            final_image = Image.new('RGBA', original_image.size, (0, 0, 0, 0))
            final_image.paste(original_image, (0, 0))
            
            PADDING_X = int(img_width * 0.1)
            PADDING_Y = int(img_height * 0.1)
            for y in range(0, img_height, wm_height + PADDING_Y):
                for x in range(0, img_width, wm_width + PADDING_X):
                    final_image.paste(watermark, (x, y), mask=watermark)

            buffer = BytesIO()
            final_image.convert("RGB").save(buffer, format='JPEG', quality=90)
            buffer.seek(0)
            
            file_name = os.path.basename(foto.imagem.name)
            foto.miniatura_marca_dagua.save(file_name, buffer, save=False)
            foto.save(update_fields=['miniatura_marca_dagua'])
            print(f"--- [CELERY] Miniatura para a foto {foto.id} salva com sucesso! ---")

        print(f"--- [CELERY] Processamento completo para Foto ID: {foto.id} ---")
            
    except Exception as e:
        print(f"!!!!!!!!!!!! [ERRO CELERY] Ocorreu um erro ao processar a foto ID {foto_id} !!!!!!!!!!!!")
        print(f"ERRO: {e}")


@shared_task
def gerar_miniatura_video_task(video_id):
    temp_video_path = None
    temp_thumb_path = None
    try:
        video = Video.objects.get(id=video_id)
        if not video.arquivo_video or video.miniatura:
            return

        print(f"--- [CELERY] Iniciando geração de miniatura para Vídeo ID: {video.id} ---")

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video_file, \
             tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_thumb_file:
            temp_video_path = temp_video_file.name
            temp_thumb_path = temp_thumb_file.name
        
        print(f"--- [CELERY] Baixando vídeo do S3 para um ficheiro temporário... ---")
        with video.arquivo_video.open('rb') as s3_video_file:
            with open(temp_video_path, 'wb') as local_video_file:
                local_video_file.write(s3_video_file.read())

        print(f"--- [CELERY] Extraindo frame com FFmpeg do ficheiro local... ---")
        (
            ffmpeg
            .input(temp_video_path, ss=1)
            .output(temp_thumb_path, vframes=1)
            .overwrite_output()
            .run(cmd='C:/ffmpeg/bin/ffmpeg.exe', capture_stdout=True, capture_stderr=True) # Confirme se este caminho do ffmpeg está correto
        )

        with open(temp_thumb_path, 'rb') as thumb_f:
            file_name = os.path.basename(video.arquivo_video.name).split('.')[0] + '.jpg'
            video.miniatura.save(file_name, ContentFile(thumb_f.read()), save=True)
        
        print(f"--- [CELERY] Miniatura para o Vídeo {video.id} salva com sucesso! ---")

    except Exception as e:
        print(f"!!!!!!!!!!!! [ERRO CELERY] Ocorreu um erro ao processar o vídeo ID {video_id} !!!!!!!!!!!!")
        if isinstance(e, ffmpeg.Error):
            print('stdout:', e.stdout.decode('utf8'))
            print('stderr:', e.stderr.decode('utf8'))
        else:
            print(f"ERRO: {e}")
    finally:
        print(f"--- [CELERY] Limpando ficheiros temporários... ---")
        if temp_video_path and os.path.exists(temp_video_path):
            os.remove(temp_video_path)
        if temp_thumb_path and os.path.exists(temp_thumb_path):
            os.remove(temp_thumb_path)