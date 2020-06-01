""" Store packages in S3 """
import logging
from binascii import hexlify
from contextlib import contextmanager
from hashlib import md5
from io import BytesIO
from urllib.request import urlopen

from pyramid.httpexceptions import HTTPFound
from pyramid.settings import asbool

from pypicloud.models import Package

from .base import IStorage

LOG = logging.getLogger(__name__)


class ObjectStoreStorage(IStorage):

    """ Storage backend base class containing code that is common between
        supported object stores (S3 / GCS)
    """

    test = False

    def __init__(
        self,
        request=None,
        bucket=None,
        expire_after=None,
        bucket_prefix=None,
        prepend_hash=None,
        redirect_urls=None,
        sse=None,
        object_acl=None,
        storage_class=None,
        region_name=None,
        public_url=False,
        **kwargs
    ):
        super(ObjectStoreStorage, self).__init__(request, **kwargs)
        self.bucket = bucket
        self.expire_after = expire_after
        self.bucket_prefix = bucket_prefix
        self.prepend_hash = prepend_hash
        self.redirect_urls = redirect_urls
        self.sse = sse
        self.object_acl = object_acl
        self.storage_class = storage_class
        self.region_name = region_name
        self.public_url = public_url

    @classmethod
    def get_bucket(cls, bucket_name: str, settings):
        """ Subclasses must implement a method for generating a Bucket class
            instance in the backend's SDK
        """
        raise NotImplementedError

    def _generate_url(self, package: Package) -> str:
        """ Subclasses must implement a method for generating signed URLs to
            the package in the object store
        """
        raise NotImplementedError

    @classmethod
    def package_from_object(cls, obj, factory):
        """ Subclasses must implement a method for constructing a Package
            instance from the backend's storage object format
        """
        raise NotImplementedError

    @classmethod
    def _subclass_specific_config(cls, settings, common_config):
        """ Method to allow subclasses to extract configuration parameters
            specific to them and not covered in the common configuration
            in this class.
        """
        return {}

    @classmethod
    def configure(cls, settings):
        kwargs = super(ObjectStoreStorage, cls).configure(settings)
        kwargs["expire_after"] = int(settings.get("storage.expire_after", 60 * 60 * 24))
        kwargs["bucket_prefix"] = settings.get("storage.prefix", "")
        kwargs["prepend_hash"] = asbool(settings.get("storage.prepend_hash", True))
        kwargs["object_acl"] = settings.get("storage.object_acl", None)
        kwargs["storage_class"] = storage_class = settings.get("storage.storage_class")
        kwargs["redirect_urls"] = asbool(settings.get("storage.redirect_urls", True))
        bucket_name = settings.get("storage.bucket")
        if bucket_name is None:
            raise ValueError("You must specify the 'storage.bucket'")
        kwargs["bucket"] = cls.get_bucket(bucket_name, settings)

        kwargs["region_name"] = settings.get("storage.region_name")
        kwargs["public_url"] = asbool(settings.get("storage.public_url"))

        kwargs.update(cls._subclass_specific_config(settings, kwargs))
        return kwargs

    def calculate_path(self, package):
        """ Calculates the path of a package """
        path = package.name + "/" + package.filename
        if self.prepend_hash:
            m = md5()
            m.update(package.filename.encode("utf-8"))
            prefix = hexlify(m.digest()).decode("utf-8")[:4]
            path = prefix + "/" + path
        return path

    def get_path(self, package):
        """ Get the fully-qualified bucket path for a package """
        if "path" not in package.data:
            filename = self.calculate_path(package)
            package.data["path"] = self.bucket_prefix + filename
        return package.data["path"]

    def get_url(self, package):
        if self.redirect_urls:
            return super(ObjectStoreStorage, self).get_url(package)
        else:
            return self._generate_url(package)

    def download_response(self, package):
        return HTTPFound(location=self._generate_url(package))

    @contextmanager
    def open(self, package):
        url = self._generate_url(package)
        handle = urlopen(url)
        try:
            yield BytesIO(handle.read())
        finally:
            handle.close()
