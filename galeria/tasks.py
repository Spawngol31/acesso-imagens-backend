import ftplib
import os
import boto3
import ffmpeg
import tempfile
import shutil
import subprocess
from io import BytesIO
from PIL import Image, ImageOps
from django.db.models import Q

from celery import shared_task
from django.core.files.storage import default_storage
from django.conf import settings
from django.core.files.base import ContentFile
from .models import Foto, FaceIndexada, Video 
from contas.models import JornalParceiro
from loja.models import ItemPedido

# ====================================================================
# TAREFA DE PROCESSAMENTO BÁSICO (Redimensionar, Rekognition, Marca d'água)
# ====================================================================
@shared_task
def processar_foto_task(foto_id):
    try:
        foto = Foto.objects.get(id=foto_id)
        if not foto.imagem:
            return

        print(f"--- [CELERY] Iniciando processamento rápido para Foto ID: {foto.id} ---")

        # 1. Faz o download da imagem do Cloudflare R2 para a memória
        with foto.imagem.open('rb') as image_file:
            image_bytes = image_file.read()

        # 2. ABRE A IMAGEM APENAS UMA VEZ
        img_original = Image.open(BytesIO(image_bytes))
        img_original = ImageOps.exif_transpose(img_original) 

        # 3. OTIMIZAÇÃO EXTREMA PARA A AWS REKOGNITION
        if not foto.faces_indexadas.exists():
            img_rek = img_original.copy()
            img_rek.thumbnail((800, 800), Image.Resampling.LANCZOS)
            
            buffer_rek = BytesIO()
            img_rek.convert('RGB').save(buffer_rek, format='JPEG', quality=85)
            
            # 🚨 MUDANÇA 1: Forçar o Rekognition a usar as credenciais específicas da AWS
            rekognition_client = boto3.client(
                'rekognition', 
                aws_access_key_id=settings.AWS_REKOGNITION_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_REKOGNITION_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REKOGNITION_REGION_NAME
            )
            
            response = rekognition_client.index_faces(
                CollectionId=settings.AWS_REKOGNITION_COLLECTION_ID,
                Image={'Bytes': buffer_rek.getvalue()}, 
                ExternalImageId=str(foto.id),
                MaxFaces=6,           
                QualityFilter='HIGH', 
                DetectionAttributes=['DEFAULT']
            )
            
            novas_faces = []
            for face_record in response.get('FaceRecords', []):
                face_id = face_record['Face']['FaceId']
                novas_faces.append(FaceIndexada(foto=foto, rekognition_face_id=face_id))
            
            if novas_faces:
                FaceIndexada.objects.bulk_create(novas_faces)

        # 4. CRIAÇÃO DA MARCA D'ÁGUA 
        if not foto.miniatura_marca_dagua:
            img_wm = img_original.copy().convert("RGBA")
            img_wm.thumbnail((600, 600), Image.Resampling.LANCZOS)
            
            img_width, img_height = img_wm.size
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

                final_image = Image.new('RGBA', img_wm.size, (0, 0, 0, 0))
                final_image.paste(img_wm, (0, 0))
                
                PADDING_X = int(img_width * 0.1)
                PADDING_Y = int(img_height * 0.1)
                
                for y in range(0, img_height, wm_height + PADDING_Y):
                    for x in range(0, img_width, wm_width + PADDING_X):
                        final_image.paste(watermark, (x, y), mask=watermark)

                buffer_final = BytesIO()
                final_image.convert("RGB").save(buffer_final, format='JPEG', quality=90)
                buffer_final.seek(0)
                
                file_name = os.path.basename(foto.imagem.name)
                foto.miniatura_marca_dagua.save(file_name, ContentFile(buffer_final.read()), save=True)

        img_original.close()
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

@shared_task
def processar_preview_video(video_id):
    caminho_original = None
    caminho_preview_temp = None
    caminho_wm_tiled = None
    
    try:
        video = Video.objects.get(id=video_id)
        
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_original:
            caminho_original = temp_original.name
            with video.arquivo_video.open('rb') as s3_video_file:
                temp_original.write(s3_video_file.read())

        nome_arquivo = os.path.basename(video.arquivo_video.name)
        nome_preview = f"preview_{nome_arquivo}"
        caminho_preview_temp = os.path.join(settings.MEDIA_ROOT, 'temp', nome_preview)
        os.makedirs(os.path.dirname(caminho_preview_temp), exist_ok=True)
        
        caminho_marca_dagua = os.path.join(settings.STATIC_ROOT, 'watermark.PNG')
        caminho_wm_tiled = os.path.join(settings.MEDIA_ROOT, 'temp', f'wm_tiled_{video_id}.png')
        
        with Image.open(caminho_marca_dagua).convert("RGBA") as wm:
            nova_largura = 120
            ratio = nova_largura / wm.size[0]
            nova_altura = int(wm.size[1] * ratio)
            wm = wm.resize((nova_largura, nova_altura), Image.Resampling.LANCZOS)
            
            alpha = wm.getchannel('A')
            alpha = alpha.point(lambda i: i * 0.50)
            wm.putalpha(alpha)
            
            canvas_size = 2000
            canvas = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
            
            padding_x = 40
            padding_y = 60

            for y in range(0, canvas_size, nova_altura + padding_y):
                for x in range(0, canvas_size, nova_largura + padding_x):
                    canvas.paste(wm, (x, y), mask=wm)
            
            canvas.save(caminho_wm_tiled, 'PNG')

        filtro_ffmpeg = "[0:v]scale=-2:720[bg];[bg][1:v]overlay=0:0"

        comando = [
            'ffmpeg', '-y',
            '-i', caminho_original,
            '-i', caminho_wm_tiled,
            '-t', '10',
            '-filter_complex', filtro_ffmpeg,
            '-an',
            '-c:v', 'libx264',
            '-crf', '28',
            caminho_preview_temp
        ]

        subprocess.run(comando, check=True)

        with open(caminho_preview_temp, 'rb') as f:
            video.arquivo_preview.save(nome_preview, ContentFile(f.read()), save=True)

        return f"Preview do vídeo {video_id} gerado com sucesso!"

    except Exception as e:
        print(f"Erro ao processar vídeo {video_id}: {e}")
        return False
        
    finally:
        if caminho_original and os.path.exists(caminho_original):
            os.remove(caminho_original)
        if caminho_preview_temp and os.path.exists(caminho_preview_temp):
            os.remove(caminho_preview_temp)
        if caminho_wm_tiled and os.path.exists(caminho_wm_tiled):
            os.remove(caminho_wm_tiled)

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
                
                pasta_alvo = parceiro.ftp_pasta.strip()
                if not pasta_alvo or pasta_alvo == '/':
                    pasta_alvo = 'Acesso_Imagens' 

                try:
                    ftp.cwd(pasta_alvo) 
                except ftplib.error_perm:
                    try:
                        ftp.mkd(pasta_alvo)
                        ftp.cwd(pasta_alvo)
                    except ftplib.error_perm:
                        try:
                            ftp.cwd('/')
                        except:
                            pass 

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

@shared_task
def distribuir_foto_temporaria_ftp(temp_s3_key, jornais_ids, metadados=None):
    try:
        # 🚨 MUDANÇA 2: Adicionar o Endpoint URL para o boto3 encontrar o Cloudflare R2
        s3_client = boto3.client(
            's3', 
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID, 
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY, 
            region_name=settings.AWS_S3_REGION_NAME,
            endpoint_url=settings.AWS_S3_ENDPOINT_URL 
        )
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME

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
                
                pasta_alvo = parceiro.ftp_pasta.strip()
                if not pasta_alvo or pasta_alvo == '/':
                    pasta_alvo = 'Acesso_Imagens'

                try:
                    ftp.cwd(pasta_alvo)
                except ftplib.error_perm:
                    try:
                        ftp.mkd(pasta_alvo)
                        ftp.cwd(pasta_alvo)
                    except ftplib.error_perm:
                        try:
                            ftp.cwd('/')
                        except:
                            pass

                ftp.storbinary(f'STOR {nome_arquivo}', BytesIO(img_data))
                ftp.quit()
                resultados.append(f"Enviado Temp Puro para: {parceiro.nome_jornal}")
            except Exception as e:
                resultados.append(f"Falha Temp para {parceiro.nome_jornal}: {str(e)}")

        s3_client.delete_object(Bucket=bucket_name, Key=temp_s3_key)

        return resultados

    except Exception as e:
        return f"Erro crítico na distribuição temporária: {str(e)}"

@shared_task
def apagar_midias_antigas_task(fotos_ids_list, videos_ids_list):
    """
    Tarefa de limpeza profunda. 
    1. Apaga os Vínculos Pendentes (Carrinhos Abandonados)
    2. Apaga do Amazon Rekognition
    3. Apaga da Cloudflare R2
    4. Apaga do Banco de Dados
    """
    try:
        rekognition_client = boto3.client(
            'rekognition',
            aws_access_key_id=settings.AWS_REKOGNITION_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_REKOGNITION_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REKOGNITION_REGION_NAME
        )
    except Exception as e:
        print(f"Erro ao conectar com Rekognition na limpeza: {e}")
        return False

    # --- 1. LIMPEZA DE FOTOS ---
    if fotos_ids_list:
        print(f"--- [CELERY] Apagando {len(fotos_ids_list)} fotos mortas ---")
        fotos = Foto.objects.filter(id__in=fotos_ids_list)
        
        for foto in fotos:
            try:
                # 🚨 PASSO NOVO: Quebrar a fechadura! 
                # Apaga os ItemPedidos que estão segurando a foto (desde que não estejam PAGOS)
                ItemPedido.objects.filter(foto=foto).exclude(
                    Q(pedido__status='PAGO') | Q(pedido__status='CONCLUIDO')
                ).delete()

                # A. Apagar Assinaturas Faciais da Amazon IA
                faces = FaceIndexada.objects.filter(foto=foto)
                face_ids = [face.rekognition_face_id for face in faces if face.rekognition_face_id]
                
                if face_ids:
                    rekognition_client.delete_faces(
                        CollectionId=settings.AWS_REKOGNITION_COLLECTION_ID,
                        FaceIds=face_ids
                    )
                
                # B. Apagar do R2 e Banco de Dados (Agora vai funcionar!)
                foto.delete()
                print(f"Foto {foto.id} apagada com sucesso!")
                
            except Exception as e:
                print(f"Falha ao apagar Foto {foto.id}: {e}")

    # --- 2. LIMPEZA DE VÍDEOS ---
    if videos_ids_list:
         print(f"--- [CELERY] Apagando {len(videos_ids_list)} vídeos mortos ---")
         videos = Video.objects.filter(id__in=videos_ids_list)
         
         for video in videos:
             try:
                 # 🚨 PASSO NOVO: Quebrar a fechadura para os vídeos
                 ItemPedido.objects.filter(video=video).exclude(
                     Q(pedido__status='PAGO') | Q(pedido__status='CONCLUIDO')
                 ).delete()

                 # Apaga do R2 e Banco de Dados
                 video.delete()
                 print(f"Vídeo {video.id} apagado com sucesso!")
             except Exception as e:
                 print(f"Falha ao apagar Vídeo {video.id}: {e}")

    return f"Limpeza finalizada! {len(fotos_ids_list)} fotos e {len(videos_ids_list)} vídeos apagados."