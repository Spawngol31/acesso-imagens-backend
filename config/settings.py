# config/settings.py
from pathlib import Path
from dotenv import load_dotenv
import os
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

dotenv_path = BASE_DIR / '.env'
load_dotenv(dotenv_path=dotenv_path)

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')

# Lógica de DEBUG e HOSTS
DEBUG = os.getenv('DEBUG', 'True') == 'True'

ALLOWED_HOSTS_STRING = os.getenv('DJANGO_ALLOWED_HOSTS', '')
ALLOWED_HOSTS = []
if ALLOWED_HOSTS_STRING:
    ALLOWED_HOSTS = ALLOWED_HOSTS_STRING.split(',')
if DEBUG:
    ALLOWED_HOSTS.extend(['localhost', '127.0.0.1'])

# Application definition
INSTALLED_APPS = [
    'admin_interface',
    'colorfield',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'contas.apps.ContasConfig',
    'galeria.apps.GaleriaConfig',
    'loja.apps.LojaConfig',
    'perfis.apps.PerfisConfig',
    'storages',
    'core.apps.CoreConfig',
    'rangefilter',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]
WSGI_APPLICATION = 'config.wsgi.application'

# Database
DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600
    )
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]

# Internationalization
LANGUAGE_CODE = 'pt-BR'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "assets",
]
STORAGES = {
    "default": {
        "BACKEND": "config.storages.PublicMediaStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'contas.Usuario'

# --- CONFIGURAÇÕES DE API E SEGURANÇA ---
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
}

# Configuração de CORS (Segurança entre domínios)
CORS_ALLOW_HEADERS = [
    'accept',
    'authorization',
    'content-type',
    'origin',
    'x-csrftoken',
    'x-requested-with',
]
CORS_ALLOWED_ORIGINS_STRING = os.getenv('CORS_ALLOWED_ORIGINS', '')
CORS_ALLOWED_ORIGINS = []
if CORS_ALLOWED_ORIGINS_STRING:
    CORS_ALLOWED_ORIGINS = CORS_ALLOWED_ORIGINS_STRING.split(',')
if DEBUG:
    CORS_ALLOWED_ORIGINS.extend([
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ])
CORS_ALLOW_CREDENTIALS = True

# Configuração de CSRF (Segurança para Sessões)
CSRF_TRUSTED_ORIGINS_STRING = os.getenv('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = []
if CSRF_TRUSTED_ORIGINS_STRING:
    CSRF_TRUSTED_ORIGINS = CSRF_TRUSTED_ORIGINS_STRING.split(',')
if DEBUG:
    CSRF_TRUSTED_ORIGINS.extend([
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ])

# --- CHAVES DE API EXTERNAS ---
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME')
AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME')
AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}
AWS_LOCATION = 'media'
AWS_REKOGNITION_COLLECTION_ID = os.getenv('AWS_REKOGNITION_COLLECTION_ID')
AWS_REKOGNITION_REGION_NAME = os.getenv('AWS_REKOGNITION_REGION_NAME')
MP_ACCESS_TOKEN = os.getenv('MP_ACCESS_TOKEN')
MP_WEBHOOK_SECRET = os.getenv('MP_WEBHOOK_SECRET')
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')
BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:8000')
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')

# --- CONFIGURAÇÕES DE E-MAIL ---
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')

# Usar o Gmail tanto em Desenvolvimento (local) quanto em Produção (online)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True

# Coloque aqui o e-mail do seu projeto:
EMAIL_HOST_USER = 'jbq0101@gmail.com' 

# A SENHA TEM DE ESTAR TUDO JUNTO (Sem espaços!):
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD') 

# Como o e-mail vai aparecer para o cliente
DEFAULT_FROM_EMAIL = 'Acesso Imagens <jbq0101@gmail.com>'

# --- SEGURANÇA EM PRODUÇÃO (HTTPS) ---
if not DEBUG:
    # Diz ao Django para confiar no proxy do servidor (Render)
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    
    # Exige que os cookies de login e formulários só trafeguem via HTTPS
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # ==============================================================================
# --- CONFIGURAÇÕES DE OTIMIZAÇÃO DO CELERY (FILA E MEMÓRIA) ---
# ==============================================================================

# 1. Conexão com o Redis (substitua pela sua URL real do Redis se for diferente)
CELERY_BROKER_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# 2. FILA INDIANA E PREVENÇÃO DE TRAVAMENTOS (OOM - Out of Memory)
# Diz ao worker para pegar estritamente 1 tarefa de cada vez.
# Isso impede que ele tente abraçar o mundo e travar a RAM do servidor de 2GB.
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# 3. RECUPERAÇÃO DE FALHAS
# Se o servidor cair, reiniciar ou faltar RAM a meio de um processamento,
# o Celery NÃO marca a tarefa como concluída. A foto volta para a fila!
CELERY_ACKS_LATE = True

# 4. TIMEOUTS E LIMPEZA
# Se uma foto demorar mais de 1 hora a processar, algo correu mal.
# Ele aborta e devolve à fila.
broker_transport_options = {'visibility_timeout': 900}

# Formato padrão de envio de mensagens
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'