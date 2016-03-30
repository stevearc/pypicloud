""" Store packages in GCS """
import calendar
import logging
import posixpath
import time
from contextlib import contextmanager
from hashlib import md5
from urllib import urlopen, quote

from boto.gs.key import Key
import gcs_oauth2_boto_plugin
import boto.gs
from pyramid.httpexceptions import HTTPFound
from pyramid.settings import asbool

from .base import IStorage
from pypicloud.models import Package
from pypicloud.util import parse_filename, getdefaults


LOG = logging.getLogger(__name__)

SUPPORTED_CALLING_FORMATS = {
    'SubdomainCallingFormat': boto.s3.connection.SubdomainCallingFormat,
    'VHostCallingFormat': boto.s3.connection.VHostCallingFormat,
    'OrdinaryCallingFormat': boto.s3.connection.OrdinaryCallingFormat,
    'ProtocolIndependentOrdinaryCallingFormat':
        boto.s3.connection.ProtocolIndependentOrdinaryCallingFormat
}


class GCSStorage(IStorage):

    """ Storage backend that uses GCS """
    test = False

    def __init__(self, request=None, bucket=None, expire_after=None,
                 bucket_prefix=None, prepend_hash=None, redirect_urls=None,
                 **kwargs):
        super(GCSStorage, self).__init__(request, **kwargs)
        self.bucket = bucket
        self.expire_after = expire_after
        self.bucket_prefix = bucket_prefix
        self.prepend_hash = prepend_hash
        self.redirect_urls = redirect_urls

    @classmethod
    def configure(cls, settings):
        kwargs = super(GCSStorage, cls).configure(settings)
        kwargs['expire_after'] = int(getdefaults(
            settings, 'storage.expire_after', 'aws.expire_after', 60 * 60 *
            24))
        kwargs['bucket_prefix'] = getdefaults(
            settings, 'storage.prefix', 'aws.prefix', '')
        kwargs['prepend_hash'] = asbool(getdefaults(
            settings, 'storage.prepend_hash', 'aws.prepend_hash', True))
        is_secure = getdefaults(settings, 'storage.is_secure',
                                'aws.is_secure', True)
        calling_format = settings.get('storage.calling_format',
                                      'SubdomainCallingFormat')
        bucket_name = settings.get('storage.bucketname')
        kwargs['redirect_urls'] = asbool(settings.get('storage.redirect_urls',
                                                      False))

        if calling_format not in SUPPORTED_CALLING_FORMATS:
            raise ValueError("Only {0} are supported for calling_format"
                             .format(', '.join(SUPPORTED_CALLING_FORMATS)))

        bucket = getdefaults(settings, 'storage.bucket', 'aws.bucket',
                                 None)
        if bucket is None:
            raise ValueError("You must specify the 'storage.bucket'")
        bucket = boto.storage_uri(bucket, 'gs')
        bucket = bucket.get_bucket()
        kwargs['bucket'] = bucket
        return kwargs

    def calculate_path(self, package):
        """ Calculates the path of a package """
        path = package.name + '/' + package.filename
        if self.prepend_hash:
            m = md5()
            m.update(package.filename)
            prefix = m.digest().encode('hex')[:4]
            path = prefix + '/' + path
        return path

    def get_path(self, package):
        """ Get the fully-qualified bucket path for a package """
        if 'path' not in package.data:
            filename = self.calculate_path(package)
            package.data['path'] = self.bucket_prefix + filename
        return package.data['path']

    def list(self, factory=Package):
        keys = self.bucket
        for key in keys:
            # Moto doesn't send down metadata from bucket.list()
            if self.test:
                key = self.bucket.get_key(key.key)
            filename = posixpath.basename(key.key)
            name = key.get_metadata('name')
            version = key.get_metadata('version')

            # We used to not store metadata. This is for backwards
            # compatibility
            if name is None or version is None:
                try:
                    name, version = parse_filename(filename)
                except ValueError:
                    LOG.warning("GCS file %s has no package name", key.key)
                    continue

            last_modified = boto.utils.parse_ts(key.last_modified)

            pkg = factory(name, version, filename, last_modified, path=key.key)

            yield pkg

    def _generate_url(self, package):
        """ Generate a signed url to the GCS file """
        key = Key(self.bucket, self.get_path(package))
        return key.generate_url(self.expire_after)

    def get_url(self, package):
        if self.redirect_urls:
            return super(GCSStorage, self).get_url(package)
        else:
            return self._generate_url(package)

    def download_response(self, package):
        return HTTPFound(location=self._generate_url(package))

    def upload(self, package, data):
        key = Key(self.bucket)
        key.key = self.get_path(package)
        key.set_metadata('name', package.name)
        key.set_metadata('version', package.version)
        key.set_contents_from_string(data.read())

    def delete(self, package):
        path = self.get_path(package)
        key = Key(self.bucket)
        key.key = path
        key.delete()

    @contextmanager
    def open(self, package):
        url = self._generate_url(package)
        handle = urlopen(url)
        try:
            yield handle
        finally:
            handle.close()
