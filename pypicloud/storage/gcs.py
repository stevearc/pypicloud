""" Store packages in GCS """
import posixpath

import logging
from google.cloud import storage

from .object_store import ObjectStoreStorage
from pypicloud.models import Package


LOG = logging.getLogger(__name__)


class GoogleCloudStorage(ObjectStoreStorage):

    """ Storage backend that uses GCS """
    test = False

    @classmethod
    def get_bucket(cls, bucket_name, settings):
        client = storage.Client()

        bucket = client.bucket(bucket_name)

        if not bucket.exists():
            LOG.info("Creating GCS bucket %s", bucket_name)

            bucket.location = self.region_name

            bucket.create()

        return bucket


    @classmethod
    def package_from_object(blob, factory):
        """ Create a package from a GCS object """
        filename = posixpath.basename(blob.name)
        name = blob.metadata.get('name')
        version = blob.metadata.get('version')
        summary = blob.metadata.get('summary')

        return factory(name, version, filename, blob.updated, summary,
                       path=blob.name)


    def list(self, factory=Package):
        blobs = self.bucket.list_blobs(prefix=self.bucket_prefix)
        for blob in blobs:
            pkg = self.package_from_object(blob, factory)
            if pkg is not None:
                yield pkg

    def _generate_url(self, package):
        """ Generate a signed url to the GCS file """
        if self.public_url:
            # TODO
            raise NotImplementedError

        blob = self.get_gcs_blob(package)
        return blob.generate_signed_url(
                expiration=self.expire_after,
                )

    def get_gcs_blob(self, package):
        return self.bucket.blob(self.get_path(package))

    def upload(self, package, datastream):
        metadata = {
            'name': package.name,
            'version': package.version,
        }
        if package.summary:
            metadata['summary'] = package.summary

        blob = self.get_gcs_blob(package)

        blob.metadata = metadata

        blob.upload_from_file(
            datastream,
            predefined_acl = self.object_acl)

        if self.storage_class is not None:
            blob.update_storage_class(self.storage_class)

    def delete(self, package):
        blob = self.get_gcs_blob(package)
        blob.delete()
