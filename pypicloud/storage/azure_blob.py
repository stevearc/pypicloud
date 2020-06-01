""" Store packages in Azure Blob Storage """
import logging
import posixpath
from contextlib import contextmanager
from datetime import datetime, timedelta
from io import BytesIO
from urllib.request import urlopen

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobSasPermissions, BlobServiceClient, generate_blob_sas
from pyramid.httpexceptions import HTTPFound
from pyramid.settings import asbool

from pypicloud.models import Package
from pypicloud.util import normalize_metadata

from .base import IStorage

LOG = logging.getLogger(__name__)


class AzureBlobStorage(IStorage):
    """ Storage backend that uses Azure Blob Storage """

    test = False

    def __init__(
        self,
        request,
        expire_after=None,
        path_prefix=None,
        redirect_urls=None,
        storage_account_name=None,
        storage_account_key=None,
        storage_container_name=None,
    ):
        super(AzureBlobStorage, self).__init__(request)

        self.expire_after = expire_after
        self.path_prefix = path_prefix
        self.redirect_urls = redirect_urls
        self.storage_account_name = storage_account_name
        self.storage_account_key = storage_account_key
        self.storage_container_name = storage_container_name
        self.azure_storage_account_url = "https://{}.blob.core.windows.net".format(
            storage_account_name
        )
        self.blob_service_client = BlobServiceClient(
            account_url=self.azure_storage_account_url,
            credential=self.storage_account_key,
        )
        self.container_client = self.blob_service_client.get_container_client(
            self.storage_container_name
        )

    @classmethod
    def configure(cls, settings):
        kwargs = super(AzureBlobStorage, cls).configure(settings)
        kwargs["expire_after"] = int(settings.get("storage.expire_after", 60 * 60 * 24))
        kwargs["path_prefix"] = settings.get("storage.prefix", "")
        kwargs["redirect_urls"] = asbool(settings.get("storage.redirect_urls", True))
        kwargs["storage_account_name"] = settings.get("storage.storage_account_name")
        if kwargs["storage_account_name"] is None:
            raise ValueError("You must specify the 'storage.storage_account_name'")

        kwargs["storage_account_key"] = settings.get("storage.storage_account_key")
        if kwargs["storage_account_key"] is None:
            raise ValueError("You must specify the 'storage.storage_account_key'")

        kwargs["storage_container_name"] = settings.get(
            "storage.storage_container_name"
        )
        if kwargs["storage_container_name"] is None:
            raise ValueError("You must specify the 'storage.storage_container_name'")

        return kwargs

    def _generate_url(self, package: Package) -> str:
        path = self.get_path(package)

        url_params = generate_blob_sas(
            account_name=self.storage_account_name,
            container_name=self.storage_container_name,
            blob_name=path,
            account_key=self.storage_account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now() + timedelta(seconds=self.expire_after),
            protocol="https",
        )

        url = "{}/{}/{}?{}".format(
            self.azure_storage_account_url,
            self.storage_container_name,
            path,
            url_params,
        )
        return url

    def download_response(self, package):
        return HTTPFound(location=self._generate_url(package))

    def list(self, factory=Package):
        # List does not return metadata :(
        for blob_properties in self.container_client.list_blobs(
            name_starts_with=self.path_prefix
        ):
            blob_client = self.container_client.get_blob_client(
                blob=blob_properties.name
            )
            metadata = blob_client.get_blob_properties()

            yield factory(
                metadata.metadata["name"],
                metadata.metadata["version"],
                posixpath.basename(blob_properties.name),
                blob_properties.last_modified,
                path=blob_properties.name,
                **Package.read_metadata(metadata.metadata)
            )

    def get_path(self, package):
        """ Get the fully-qualified bucket path for a package """
        if "path" not in package.data:
            package.data["path"] = (
                self.path_prefix + package.name + "/" + package.filename
            )
        return package.data["path"]

    def upload(self, package, datastream):
        path = self.get_path(package)

        metadata = package.get_metadata()
        metadata["name"] = package.name
        metadata["version"] = package.version
        normalize_metadata(metadata)

        blob_client = self.container_client.get_blob_client(blob=path)
        blob_client.upload_blob(data=datastream, metadata=metadata)

    def delete(self, package):
        path = self.get_path(package)
        blob_client = self.container_client.get_blob_client(blob=path)
        blob_client.delete_blob()

    def check_health(self):
        try:
            self.container_client.get_blob_client(
                blob="__notexist"
            ).get_blob_properties()
        except ResourceNotFoundError:
            pass
        except Exception as e:
            return False, str(e)
        return True, ""

    @contextmanager
    def open(self, package):
        url = self._generate_url(package)
        handle = urlopen(url)
        try:
            yield BytesIO(handle.read())
        finally:
            handle.close()
