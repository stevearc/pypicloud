""" Storage backend implementations """
from functools import partial
from typing import Any, Callable

from pyramid.path import DottedNameResolver

from .base import IStorage
from .files import FileStorage
from .s3 import CloudFrontS3Storage, S3Storage

try:
    from .gcs import GoogleCloudStorage

    GCS_IS_AVAILABLE = True
except ImportError:
    GCS_IS_AVAILABLE = False

try:
    from .azure_blob import AzureBlobStorage

    AZURE_BLOB_IS_AVAILABLE = True
except ImportError:
    AZURE_BLOB_IS_AVAILABLE = False


def get_storage_impl(settings) -> Callable[[Any], Any]:
    """ Get and configure the storage backend wrapper """
    resolver = DottedNameResolver(__name__)
    storage = settings.get("pypi.storage", "file")
    if storage == "azure-blob":
        if not AZURE_BLOB_IS_AVAILABLE:
            raise ValueError(
                "azure-blob storage backend selected but Azure Blob "
                "Storage is not available. "
                "Please install the azure-storage-blob library by "
                "including the `azure-blob` extra in your pip-install step. "
                "For example: `pip install pypicloud[azure-blob]`"
            )

        storage = "pypicloud.storage.AzureBlobStorage"
    elif storage == "s3":
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
