"""
Django settings for Filial 16 project.
Credenciais e valores sensíveis vêm de variáveis de ambiente (.env em produção).
"""
import os
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv

# Carrega .env na raiz do projeto (desenvolvimento e produção)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'dev-secret-change-in-production-filial16'
)

DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

CSRF_TRUSTED_ORIGINS = [
    x.strip() for x in os.environ.get(
        'CSRF_TRUSTED_ORIGINS',
        'http://localhost:8000,http://127.0.0.1:8000'
    ).split(',') if x.strip()
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'storages',
    'fila',
    'core',
    'regras_api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'filial16.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'fila.context_processors.total_fila',
                'fila.context_processors.menu_permissions',
            ],
        },
    },
]

WSGI_APPLICATION = 'filial16.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'filial16'),
        'USER': os.environ.get('POSTGRES_USER', 'filial16'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'filial16'),
        'HOST': os.environ.get('POSTGRES_HOST', 'db'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        'OPTIONS': {},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = []

# MinIO via django-storages + boto3
_MINIO_ENDPOINT = os.environ.get('MINIO_ENDPOINT', 'localhost:9000')
_MINIO_ACCESS = os.environ.get('MINIO_ACCESS_KEY', 'filial16')
_MINIO_SECRET = os.environ.get('MINIO_SECRET_KEY', 'filial16minio')
_MINIO_BUCKET = os.environ.get('MINIO_BUCKET', 'filial16')
_MINIO_SSL = os.environ.get('MINIO_USE_SSL', '0').lower() in ('1', 'true', 'yes')

AWS_ACCESS_KEY_ID = _MINIO_ACCESS
AWS_SECRET_ACCESS_KEY = _MINIO_SECRET
AWS_STORAGE_BUCKET_NAME = _MINIO_BUCKET
AWS_S3_ENDPOINT_URL = f"{'https' if _MINIO_SSL else 'http'}://{_MINIO_ENDPOINT}"
AWS_S3_USE_SSL = _MINIO_SSL
AWS_DEFAULT_ACL = None
AWS_S3_FILE_OVERWRITE = True
AWS_LOCATION = ''  # sem prefixo automático
AWS_QUERYSTRING_AUTH = False

# default = MinIO: todos os uploads de media (fotos, documentos de motorista/cavalo/carreta etc.) vão para o bucket
STORAGES = {
    'default': {
        'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

MEDIA_URL = '/media/'

# Upload de PDFs grandes (ex.: processador OST + integração n8n)
# DATA_UPLOAD: corpo inteiro do POST; FILE_UPLOAD: buffer em memória antes de ir ao disco
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.environ.get('DATA_UPLOAD_MAX_MEMORY_SIZE', 250 * 1024 * 1024))  # 250 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = int(os.environ.get('FILE_UPLOAD_MAX_MEMORY_SIZE', 50 * 1024 * 1024))   # 50 MB (guia n8n)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'login'

# REST Framework: API Key (n8n, X-Api-Key) → JWT (app) → Sessão (navegador)
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'fila.api_key_auth.ApiKeyAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
}

# Google Sheets (Agregamento - Cavalos)
GOOGLE_SHEETS_ENABLED = os.environ.get('GOOGLE_SHEETS_ENABLED', '0').lower() in ('1', 'true', 'yes')
GOOGLE_SHEETS_CREDENTIALS_PATH = os.environ.get('GOOGLE_SHEETS_CREDENTIALS_PATH', '')
GOOGLE_SHEETS_SPREADSHEET_ID = os.environ.get('GOOGLE_SHEETS_SPREADSHEET_ID', '')
GOOGLE_SHEETS_WORKSHEET_NAME = os.environ.get('GOOGLE_SHEETS_WORKSHEET_NAME', 'Cavalos')
