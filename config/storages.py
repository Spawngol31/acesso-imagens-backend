# config/storages.py
from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings

class PublicMediaStorage(S3Boto3Storage):
    location = 'media'
    file_overwrite = False
    endpoint_url = settings.AWS_S3_ENDPOINT_URL

class PrivateMediaStorage(S3Boto3Storage):
    location = 'media_private'
    file_overwrite = False
    custom_domain = False
    endpoint_url = settings.AWS_S3_ENDPOINT_URL