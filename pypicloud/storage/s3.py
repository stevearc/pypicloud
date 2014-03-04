""" Store packages in S3 """
import time
from datetime import datetime

import logging
from hashlib import md5
from pyramid.httpexceptions import HTTPNotFound
from pyramid.settings import asbool

import boto
import os
from .base import IStorage
from boto.s3.key import Key
from pip.util import splitext


LOG = logging.getLogger(__name__)


class S3Storage(IStorage):

    """ Storage backend that uses S3 """
    bucket = None
    test = False

    @classmethod
    def configure(cls, config):
        super(S3Storage, cls).configure(config)
        settings = config.get_settings()
        cls.expire_after = int(settings.get('aws.expire_after', 60 * 60 * 24))
        cls.buffer_time = int(settings.get('aws.buffer_time', 600))
        cls.bucket_prefix = settings.get('aws.prefix', '')
        cls.prepend_hash = asbool(settings.get('aws.prepend_hash', True))

        s3conn = boto.connect_s3(
            aws_access_key_id=settings.get('aws.access_key'),
            aws_secret_access_key=settings.get('aws.secret_key'))
        aws_bucket = settings['aws.bucket']
        cls.bucket = s3conn.lookup(aws_bucket, validate=False)
        if cls.bucket is None:
            location = settings.get('aws.region',
                                    boto.s3.connection.Location.DEFAULT)
            cls.bucket = s3conn.create_bucket(aws_bucket, location=location)

    @staticmethod
    def parse_package_and_version(path):
        """ Parse the package name and version number from a path """
        filename = splitext(path)[0]
        if '-' not in filename:
            return None, None
        path_components = filename.split('-')
        for i, comp in enumerate(path_components):
            if comp[0].isdigit():
                return ('_'.join(path_components[:i]).lower(),
                        '-'.join(path_components[i:]))
        return None, None

    def list(self, factory):
        keys = self.bucket.list(self.bucket_prefix)
        for key in keys:
            # Moto doesn't send down metadata from bucket.list()
            if self.test:
                key = self.bucket.get_key(key.key)
            name = key.get_metadata('name')
            version = key.get_metadata('version')

            # We used to not store metadata. This is for backwards
            # compatibility
            if name is None or version is None:
                filename = os.path.basename(key.key)
                name, version = self.parse_package_and_version(filename)

            if name is None or version is None:
                LOG.warning("S3 file %s has no package name", key.key)
                continue

            last_modified = boto.utils.parse_ts(key.last_modified)

            pkg = factory(name, version, key.key, last_modified)

            yield pkg

    def get_url(self, package):
        expire = package.data.get('expire', 0)
        changed = False
        if 'url' not in package.data or time.time() > expire:
            key = Key(self.bucket)
            key.key = package.path
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

    def upload(self, name, version, filename, data):
        key = Key(self.bucket)
        if self.prepend_hash:
            m = md5()
            m.update(name)
            m.update(version)
            prefix = m.digest().encode('hex')[:4]
            filename = prefix + '/' + filename
        key.key = self.bucket_prefix + filename
        key.set_metadata('name', name)
        key.set_metadata('version', version)
        key.set_contents_from_file(data)
        return key.key

    def delete(self, path):
        key = Key(self.bucket)
        key.key = path
        key.delete()
