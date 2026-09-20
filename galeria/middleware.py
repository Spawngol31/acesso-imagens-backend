# galeria/middleware.py

import traceback
import requests
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings

class NotificacaoBugMiddleware(MiddlewareMixin):
    def process_exception(self, request, exception):
        # Apanha a URL onde o cliente estava e o tipo de erro
        erro_resumo = str(exception)
        
        # Monta a mensagem que vai receber no seu telemóvel
        mensagem = {
            "content": f"🚨 **ALERTA DE BUG NO SITE!** 🚨\n\n**Onde ocorreu:** `{request.build_absolute_uri()}`\n**Ação:** `{request.method}`\n**O que falhou:**\n```python\n{erro_resumo}\n```\n_Verifique os logs do servidor na Hetzner para ver o erro completo._"
        }
        
        # Tenta puxar o link secreto do seu settings.py
        webhook_url = getattr(settings, 'DISCORD_WEBHOOK_URL', None)
        
        if webhook_url:
            try:
                # Dispara a mensagem instantaneamente
                requests.post(webhook_url, json=mensagem, timeout=5)
            except:
                # Ignora se houver falha de internet, para não travar a navegação do cliente
                pass 
        
        return None