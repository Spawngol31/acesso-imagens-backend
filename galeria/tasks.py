# galeria/tasks.py
import ftplib
import os
import boto3
import ffmpeg
import tempfile
import shutil
from io import BytesIO
from PIL import Image

from celery import shared_task
from django.core.files.storage import default_storage
from django.conf import settings
from django.core.files.base import ContentFile
from .models import Foto, FaceIndexada, Video 
from contas.models import JornalParceiro

# ====================================================================
# TAREFA DE PROCESSAMENTO BÁSICO (Redimensionar, Rekognition, Marca d'água)
# ====================================================================
@shared_task
def processar_foto_task(foto_id):
    try:
        foto = Foto.objects.get(id=foto_id)
        if not foto.imagem:
            return

        print(f"--- [CELERY] Iniciando processamento para Foto ID: {foto.id} ---")

        with foto.imagem.open('rb') as image_file:
            image_bytes = image_file.read()
        
        REKOGNITION_LIMIT = 5 * 1024 * 1024 # 5MB
        
        if len(image_bytes) > REKOGNITION_LIMIT:
            img = Image.open(BytesIO(image_bytes))
            img.thumbnail((1920, 1080), Image.Resampling.LANCZOS)
            buffer_rekognition = BytesIO()
            img.save(buffer_rekognition, format='JPEG', quality=95)
            image_bytes_for_rekognition = buffer_rekognition.getvalue()
        else:
            image_bytes_for_rekognition = image_bytes

        if not foto.faces_indexadas.exists():
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

        if not foto.miniatura_marca_dagua:
            with Image.open(BytesIO(image_bytes)).convert("RGBA") as original_image:
                size = (600, 600)
                original_image.thumbnail(size)
                img_width, img_height = original_image.size
                watermark_path = os.path.join(settings.STATIC_ROOT, 'watermark.PNG')
                
                with Image.open(watermark_path).convert("RGBA") as watermark:
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
                    foto.miniatura_marca_dagua.save(file_name, ContentFile(buffer.read()), save=True)

        print(f"--- [CELERY] Processamento completo para Foto ID: {foto.id} ---")
            
    except Exception as e:
        print(f"--- [ERRO CELERY] Erro ao processar foto task: {e} ---")


@shared_task
def gerar_miniatura_video_task(video_id):
    temp_video_path = None
    temp_thumb_path = None
    try:
        video = Video.objects.get(id=video_id)
        if not video.arquivo_video or video.miniatura:
            return

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video_file, \
             tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_thumb_file:
            temp_video_path = temp_video_file.name
            temp_thumb_path = temp_thumb_file.name
        
        with video.arquivo_video.open('rb') as s3_video_file:
            with open(temp_video_path, 'wb') as local_video_file:
                local_video_file.write(s3_video_file.read())

        ffmpeg_cmd = shutil.which('ffmpeg') or 'ffmpeg'
        (
            ffmpeg
            .input(temp_video_path, ss=1)
            .output(temp_thumb_path, vframes=1)
            .overwrite_output()
            .run(cmd=ffmpeg_cmd, capture_stdout=True, capture_stderr=True)
        )

        with open(temp_thumb_path, 'rb') as thumb_f:
            file_name = os.path.basename(video.arquivo_video.name).split('.')[0] + '.jpg'
            video.miniatura.save(file_name, ContentFile(thumb_f.read()), save=True)

    except Exception as e:
        print(f"--- [ERRO CELERY] Erro ao processar vídeo task: {e} ---")
    finally:
        if temp_video_path and os.path.exists(temp_video_path):
            os.remove(temp_video_path)
        if temp_thumb_path and os.path.exists(temp_thumb_path):
            os.remove(temp_thumb_path)


# ====================================================================
# TAREFA: FTP PARA FOTOS SALVAS NO SITE (Envio Direto / Sem Alteração)
# ====================================================================
@shared_task
def distribuir_foto_para_ftps(foto_id, jornais_ids=None, metadados=None):
    try:
        foto = Foto.objects.select_related('album').get(id=foto_id)
        
        if jornais_ids:
            parceiros = JornalParceiro.objects.filter(id__in=jornais_ids, ativo=True)
        else:
            parceiros = JornalParceiro.objects.filter(ativo=True)

        if not parceiros.exists():
            return "Nenhum jornal parceiro ativo encontrado."

        # Lê os bytes originais puros (Direto como saíram do Lightroom do fotógrafo)
        with foto.imagem.open('rb') as f:
            img_data = f.read()

        nome_arquivo = os.path.basename(foto.imagem.name)
        resultados = []

        for parceiro in parceiros:
            try:
                ftp = ftplib.FTP()
                if ':' in parceiro.ftp_host:
                    host, porta = parceiro.ftp_host.split(':')
                    ftp.connect(host, int(porta))
                else:
                    ftp.connect(parceiro.ftp_host, 21)
                    
                ftp.login(user=parceiro.ftp_user, passwd=parceiro.ftp_password)
                ftp.cwd(parceiro.ftp_pasta)
                ftp.storbinary(f'STOR {nome_arquivo}', BytesIO(img_data))
                ftp.quit()
                resultados.append(f"Enviado Puro para: {parceiro.nome_jornal}")
            except Exception as e:
                resultados.append(f"Falha ao enviar para {parceiro.nome_jornal}: {str(e)}")

        return resultados

    except Foto.DoesNotExist:
        return f"Erro: Foto {foto_id} não encontrada."
    except Exception as e:
        return f"Erro crítico na distribuição: {str(e)}"


# ====================================================================
# TAREFA: FTP PARA FOTOS TEMPORÁRIAS (Envio Direto / Sem Alteração)
# ====================================================================
@shared_task
def distribuir_foto_temporaria_ftp(temp_s3_key, jornais_ids, metadados=None):
    try:
        s3_client = boto3.client(
            's3', 
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID, 
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY, 
            region_name=settings.AWS_S3_REGION_NAME
        )
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME

        # Baixa os bytes originais salvos na pasta temporária do S3
        s3_response = s3_client.get_object(Bucket=bucket_name, Key=temp_s3_key)
        img_data = s3_response['Body'].read()

        parceiros = JornalParceiro.objects.filter(id__in=jornais_ids, ativo=True)
        nome_arquivo = temp_s3_key.split('/')[-1]
        if '_' in nome_arquivo:
            nome_arquivo = nome_arquivo.split('_', 1)[1]

        resultados = []

        for parceiro in parceiros:
            try:
                ftp = ftplib.FTP()
                if ':' in parceiro.ftp_host:
                    host, porta = parceiro.ftp_host.split(':')
                    ftp.connect(host, int(porta))
                else:
                    ftp.connect(parceiro.ftp_host, 21)
                    
                ftp.login(user=parceiro.ftp_user, passwd=parceiro.ftp_password)
                ftp.cwd(parceiro.ftp_pasta)
                ftp.storbinary(f'STOR {nome_arquivo}', BytesIO(img_data))
                ftp.quit()
                resultados.append(f"Enviado Temp Puro para: {parceiro.nome_jornal}")
            except Exception as e:
                resultados.append(f"Falha Temp para {parceiro.nome_jornal}: {str(e)}")

        # Faz a limpeza regular do S3 temporário
        s3_client.delete_object(Bucket=bucket_name, Key=temp_s3_key)

        return resultados

    except Exception as e:
        return f"Erro crítico na distribuição temporária: {str(e)}"