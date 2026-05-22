import os
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

# 1. Cria uma pasta no seu computador para simular a redação do Jornal
pasta_destino = os.path.join(os.getcwd(), "Jornal_Recebimentos")
os.makedirs(pasta_destino, exist_ok=True)

# 2. Cria as credenciais de acesso
authorizer = DummyAuthorizer()
# (Username, Password, Pasta de destino, Permissões totais)
authorizer.add_user("editor_jornal", "senha123", pasta_destino, perm="elradfmwMT")

# 3. Configura o "motor" do FTP
handler = FTPHandler
handler.authorizer = authorizer

# 4. Liga o servidor na porta 2121 (Usamos 2121 em vez de 21 para não exigir permissões de Administrador do Windows)
endereco = ("127.0.0.1", 2121)
server = FTPServer(endereco, handler)

print("="*60)
print("📡 Servidor FTP do 'Jornal Parceiro' Online!")
print(f"🌐 Host: 127.0.0.1:2121")
print(f"👤 Usuário: editor_jornal")
print(f"🔑 Senha: senha123")
print(f"📁 As fotos vão aparecer na pasta: {pasta_destino}")
print("="*60)

# Fica a ouvir infinitamente
server.serve_forever()