""" Store packages in S3 """
import logging
import time
from contextlib import contextmanager
from hashlib import md5
from urllib import urlopen

from pyramid.httpexceptions import HTTPNotFound
from pyramid.settings import asbool

import boto
import posixpath
from .base import IStorage
from boto.s3.key import Key
from pypicloud.models import Package
from pypicloud.util import parse_filename, getdefaults


LOG = logging.getLogger(__name__)


class S3Storage(IStorage):

    """ Storage backend that uses S3 """
    bucket = None
    test = False

    @classmethod
    def configure(cls, settings):
        super(S3Storage, cls).configure(settings)
        cls.expire_after = int(getdefaults(settings, 'storage.expire_after',
                                           'aws.expire_after', 60 * 60 * 24))
        cls.buffer_time = int(getdefaults(settings, 'storage.buffer_time',
                                          'aws.buffer_time', 600))
        cls.bucket_prefix = getdefaults(settings, 'storage.prefix',
                                        'aws.prefix', '')
        cls.prepend_hash = asbool(getdefaults(settings, 'storage.prepend_hash',
                                              'aws.prepend_hash', True))
        access_key = getdefaults(settings, 'storage.access_key',
                                 'aws.access_key', None)
        secret_key = getdefaults(settings, 'storage.secret_key',
                                 'aws.secret_key', None)

        s3conn = boto.connect_s3(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key)
        aws_bucket = getdefaults(settings, 'storage.bucket', 'aws.bucket',
                                 None)
        if aws_bucket is None:
            raise ValueError("You must specify the 'storage.bucket'")
        cls.bucket = s3conn.lookup(aws_bucket, validate=False)
        if cls.bucket is None:
            location = getdefaults(settings, 'storage.region', 'aws.region',
                                   boto.s3.connection.Location.DEFAULT)
            cls.bucket = s3conn.create_bucket(aws_bucket, location=location)

    def get_path(self, package):
        """ Get the fully-qualified bucket path for a package """
        if 'path' not in package.data:
            filename = package.name + '/' + package.filename
            if self.prepend_hash:
                m = md5()
                m.update(package.filename)
                prefix = m.digest().encode('hex')[:4]
                filename = prefix + '/' + filename
            package.data['path'] = self.bucket_prefix + filename
        return package.data['path']

    def list(self, factory=Package):
        keys = self.bucket.list(self.bucket_prefix)
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
                    LOG.warning("S3 file %s has no package name", key.key)
                    continue

            last_modified = boto.utils.parse_ts(key.last_modified)

            pkg = factory(name, version, filename, last_modified, path=key.key)

            yield pkg

    def get_url(self, package):
        expire = package.data.get('expire', 0)
        changed = False
        if 'url' not in package.data or time.time() > expire:
            key = Key(self.bucket)
            key.key = self.get_path(package)
            expire_after = time.time() + self.expire_after
            url = key.generate_url(expire_after, expires_in_absolute=True)
            package.data['url'] = url
            expire = expire_after - self.buffer_time
            package.data['expire'] = expire
            changed = True
        return package.data['url'], changed

    def download_response(self, package):
        # Don't need to implement because the download urls go to S3
        return HTTPNotFound()

    def upload(self, package, data):
        key = Key(self.bucket)
        key.key = self.get_path(package)
        key.set_metadata('name', package.name)
        key.set_metadata('version', package.version)
        key.set_contents_from_file(data)

    def delete(self, package):
        path = self.get_path(package)
        key = Key(self.bucket)
        key.key = path
        key.delete()

    @contextmanager
    def open(self, package):
        url = self.get_url(package)[0]
        handle = urlopen(url)
        try:
            yield handle
        finally:
            handle.close()
