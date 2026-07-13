"""
Private S3-compatible storage for artwork files.
All access is via authenticated Django views — objects are never public.
"""
from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage


class PrivateMediaStorage(S3Boto3Storage):
    location = 'artwork-media'
    default_acl = 'private'
    file_overwrite = False
    custom_domain = False
    querystring_auth = True
    querystring_expire = 3600

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('bucket_name', settings.AWS_STORAGE_BUCKET_NAME)
        super().__init__(*args, **kwargs)
