""" Store packages in GCS """
import logging
import os
import posixpath
from datetime import timedelta

from google.auth import compute_engine
from google.auth.transport import requests
from google.cloud import storage
from pyramid.settings import asbool

from pypicloud.models import Package

from .object_store import ObjectStoreStorage

LOG = logging.getLogger(__name__)


class GoogleCloudStorage(ObjectStoreStorage):

    """ Storage backend that uses GCS """

    test = False

    def __init__(
        self,
        request=None,
        service_account_json_filename=None,
        project_id=None,
        use_iam_signer=False,
        **kwargs
    ):
        super(GoogleCloudStorage, self).__init__(request=request, **kwargs)

        self.service_account_json_filename = service_account_json_filename
        self.use_iam_signer = use_iam_signer

        if self.public_url:
            raise NotImplementedError(
                "GoogleCloudStorage backend does not yet support public URLs"
            )

        if self.sse:
            raise NotImplementedError(
                "GoogleCloudStorage backend does not yet support customized "
                "server-side encryption"
            )

    @classmethod
    def _subclass_specific_config(cls, settings, common_config):
        """ Extract GCP-specific config settings: specifically, the path to
            the service account key file, and the project id.  Both are
            optional.
        """
        service_account_json_filename = settings.get(
            "storage.gcp_service_account_json_filename"
        )

        if (
            service_account_json_filename
            and not os.path.isfile(service_account_json_filename)
            and not cls.test
        ):
            raise Exception(
                "Service account json file not found at path {}".format(
                    service_account_json_filename
                )
            )

        return {
            "service_account_json_filename": service_account_json_filename,
            "project_id": settings.get("storage.gcp_project_id"),
            "use_iam_signer": asbool(settings.get("storage.gcp_use_iam_signer", False)),
        }

    @classmethod
    def _get_storage_client(cls, settings):
        """ Helper method for constructing a properly-configured GCS client
            object from the provided settings.
        """
        client_settings = cls._subclass_specific_config(settings, {})

        client_args = {}
        if client_settings["project_id"]:
            LOG.info("Using GCP project id `%s`", client_settings["project_id"])
            client_args["project"] = client_settings["project_id"]

        service_account_json_filename = client_settings.get(
            "service_account_json_filename"
        ) or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

        if not service_account_json_filename:
            LOG.info("Creating GCS client without service account JSON file")

            client = storage.Client(**client_args)
        else:
            if not os.path.isfile(service_account_json_filename) and not cls.test:
                raise Exception(
                    "Service account JSON file not found at provided "
                    "path {}".format(service_account_json_filename)
                )

            LOG.info(
                "Creating GCS client from service account JSON file %s",
                service_account_json_filename,
            )

            client = storage.Client.from_service_account_json(
                service_account_json_filename, **client_args
            )

        return client

    @classmethod
    def get_bucket(cls, bucket_name, settings):
        client = cls._get_storage_client(settings)

        bucket = client.bucket(bucket_name)

        if not bucket.exists():
            bucket.location = settings.get("storage.region_name")
            LOG.info(
                "Creating GCS bucket %s in location %s", bucket_name, bucket.location
            )
            bucket.create()

        return bucket

    @classmethod
    def package_from_object(cls, blob, factory):
        """ Create a package from a GCS object """
        filename = posixpath.basename(blob.name)
        if blob.metadata is None:
            return None
        name = blob.metadata.get("name")
        version = blob.metadata.get("version")
        if name is None or version is None:
            return None
        metadata = Package.read_metadata(blob.metadata)
        return factory(
            name, version, filename, blob.updated, path=blob.name, **metadata
        )

    def list(self, factory=Package):
        blobs = self.bucket.list_blobs(prefix=self.bucket_prefix or None)
        for blob in blobs:
            pkg = self.package_from_object(blob, factory)
            if pkg is not None:
                yield pkg

    def _generate_url(self, package):
        """ Generate a signed url to the GCS file """
        blob = self._get_gcs_blob(package)

        if self.use_iam_signer:
            # Workaround for https://github.com/googleapis/google-auth-library-python/issues/50
            signing_credentials = compute_engine.IDTokenCredentials(
                requests.Request(), ""
            )
        else:
            signing_credentials = None
        return blob.generate_signed_url(
            expiration=timedelta(seconds=self.expire_after),
            credentials=signing_credentials,
            version="v4",
        )

    def _get_gcs_blob(self, package):
        """ Get a GCS blob object for the specified package """
        return self.bucket.blob(self.get_path(package))

    def upload(self, package, datastream):
        """ Upload the package to GCS """
        metadata = {"name": package.name, "version": package.version}
        metadata.update(package.get_metadata())

        blob = self._get_gcs_blob(package)

        blob.metadata = metadata

        blob.upload_from_file(datastream, predefined_acl=self.object_acl)

        if self.storage_class is not None:
            blob.update_storage_class(self.storage_class)

    def delete(self, package):
        """ Delete the package """
        blob = self._get_gcs_blob(package)
        blob.delete()
