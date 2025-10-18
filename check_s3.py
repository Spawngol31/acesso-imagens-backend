# check_s3.py

import os
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Carrega as variáveis do seu ficheiro .env
load_dotenv()

# --- PREENCHA ESTES VALORES ---
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME')
AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME')

# --- COLE AQUI O CAMINHO DO FICHEIRO QUE VOCÊ COPIOU DO ADMIN ---
CHAVE_DO_FICHEIRO_PARA_TESTAR = "miniaturas/2025/10/05/20220604191256_IMG_0050.jpg" 
# -----------------------------------------------------------------

print("--- A TENTAR GERAR URL ASSINADA COM AS SEGUINTES CONFIGURAÇÕES: ---")
print(f"Bucket: {AWS_STORAGE_BUCKET_NAME}")
print(f"Região: {AWS_S3_REGION_NAME}")
print(f"Chave do Ficheiro: {CHAVE_DO_FICHEIRO_PARA_TESTAR}")
print("------------------------------------------------------------------")

try:
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_S3_REGION_NAME,
        config=boto3.session.Config(signature_version='s3v4')
    )

    url = s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': AWS_STORAGE_BUCKET_NAME, 'Key': CHAVE_DO_FICHEIRO_PARA_TESTAR},
        ExpiresIn=3600  # Válida por 1 hora
    )

    print("\n\nSUCESSO! URL GERADA:\n")
    print(url)
    print("\n\nCOLE ESTA URL NUMA JANELA ANÓNIMA E VEJA SE FUNCIONA.")

except ClientError as e:
    print("\n\n!!!!!!!!!!!! ERRO AO GERAR URL !!!!!!!!!!!!")
    print(f"Código do Erro: {e.response['Error']['Code']}")
    print(f"Mensagem: {e.response['Error']['Message']}")

except Exception as e:
    print(f"\n\n!!!!!!!!!!!! UM ERRO INESPERADO ACONTECEU !!!!!!!!!!!!\n{e}")
    