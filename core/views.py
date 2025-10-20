import os
from io import BytesIO
from PIL import Image
from django.conf import settings
from django.core.mail import send_mail
from django.http import HttpResponse
#from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from contas.permissions import IsFotografoOrAdmin

class ContactFormView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        nome = request.data.get('nome')
        email = request.data.get('email')
        mensagem = request.data.get('mensagem')

        if not nome or not email or not mensagem:
            return Response({'error': 'Todos os campos são obrigatórios.'}, status=status.HTTP_400_BAD_REQUEST)

        # Monta o corpo do e-mail
        corpo_email = f"""
        Nova mensagem de contato recebida:
        Nome: {nome}
        Email: {email}
        Mensagem:
        {mensagem}
        """

        try:
            send_mail(
                subject=f'Contato do Site - {nome}',
                message=corpo_email,
                from_email=settings.DEFAULT_FROM_EMAIL, # O seu e-mail de envio configurado
                recipient_list=[settings.ADMIN_EMAIL], # O e-mail que vai receber
                fail_silently=False,
            )
            return Response({'message': 'Mensagem enviada com sucesso!'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': f'Erro ao enviar e-mail: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class WatermarkToolView(APIView):
    permission_classes = [IsAuthenticated, IsFotografoOrAdmin]

    def post(self, request):
        imagem_original_file = request.FILES.get('imagem')
        if not imagem_original_file:
            return Response({'error': 'Nenhuma imagem enviada.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Reusing the watermark logic
            original_image = Image.open(imagem_original_file).convert("RGBA")
            original_image.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
            img_width, img_height = original_image.size

            watermark_path = os.path.join(settings.BASE_DIR, 'assets', 'watermark.png')
            watermark = Image.open(watermark_path).convert("RGBA")
            
            new_wm_width = int(img_width * 0.20)
            new_wm_height = int(watermark.size[1] * (new_wm_width / watermark.size[0]))
            watermark = watermark.resize((new_wm_width, new_wm_height), Image.Resampling.LANCZOS)
            wm_width, wm_height = watermark.size
            
            alpha = watermark.getchannel('A').point(lambda i: i * 0.3)
            watermark.putalpha(alpha)

            final_image = Image.new('RGBA', original_image.size, (0, 0, 0, 0))
            final_image.paste(original_image, (0, 0))
            
            for y in range(0, img_height, wm_height + int(img_height * 0.1)):
                for x in range(0, img_width, wm_width + int(img_width * 0.1)):
                    final_image.paste(watermark, (x, y), mask=watermark)

            buffer = BytesIO()
            final_image.convert("RGB").save(buffer, format='JPEG', quality=95)
            buffer.seek(0)

            original_filename = os.path.splitext(imagem_original_file.name)[0]
            download_filename = f"{original_filename}_watermarked.jpg"

            response = HttpResponse(buffer, content_type='image/jpeg')
            response['Content-Disposition'] = f'attachment; filename="{download_filename}"'
            return response

        except Exception as e:
            return Response({'error': f'Erro ao processar a imagem: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        