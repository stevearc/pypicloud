""" Storage backend implementations """
from functools import partial

from .base import IStorage
from .files import FileStorage
from .s3 import S3Storage, CloudFrontS3Storage

from pyramid.path import DottedNameResolver

try:
    from .gcs import GoogleCloudStorage

    GCS_IS_AVAILABLE = True
except ImportError:
    GCS_IS_AVAILABLE = False


def get_storage_impl(settings):
    """ Get and configure the storage backend wrapper """
    resolver = DottedNameResolver(__name__)
    storage = settings.get("pypi.storage", "file")
    if storage == "s3":
        storage = "pypicloud.storage.S3Storage"
    elif storage == "cloudfront":
        storage = "pypicloud.storage.CloudFrontS3Storage"
    elif storage == "gcs":
        if not GCS_IS_AVAILABLE:
            raise ValueError(
                "gcs backend selected but GCS is not available. "
                "Please install the google-cloud-storage library by "
                "including the `gcs` extra in your pip-install step. "
                "For example: `pip install pypicloud[gcs]`"
            )

        storage = "pypicloud.storage.GoogleCloudStorage"
    elif storage == "file":
        storage = "pypicloud.storage.FileStorage"
    storage_impl = resolver.resolve(storage)
    kwargs = storage_impl.configure(settings)
    return partial(storage_impl, **kwargs)
