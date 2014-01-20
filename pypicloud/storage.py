""" Storage backend implementations """
import os
import time
from datetime import datetime

import logging
from boto.s3.key import Key
from hashlib import md5
from pip.util import splitext
from pyramid.settings import asbool

import boto


LOG = logging.getLogger(__name__)


class IStorage(object):

    """ Interface for a backend that stores package files """

    def __init__(self, request):
        self.request = request

    @classmethod
    def configure(cls, config):
        """ Configure the storage method with app settings """

    def list(self, factory):
        """ Return a list or generator of all packages """
        raise NotImplementedError

    def get_url(self, package):
        """ Create or return an HTTP url for a package file """
        raise NotImplementedError

    def upload(self, name, version, filename, data):
        """
        Upload a package file to the storage backend

        Parameters
        ----------
        name : str
            The name of the package
        version : str
            The version of the package
        filename : str
            The name of the package file that was uploaded
        data : file
            A temporary file object that contains the package data

        Returns
        -------
        path : str
            The unique path to the file in the storage backend

        """
        raise NotImplementedError

    def delete(self, path):
        """
        Delete a package file

        Parameters
        ----------
        path : str
            The unique path to the package

        """
        raise NotImplementedError


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
        if package.url is None or datetime.utcnow() > package.expire:
            key = Key(self.bucket)
            key.key = package.path
            expire_after = time.time() + self.expire_after
            package.url = key.generate_url(expire_after,
                                           expires_in_absolute=True)
            package.expire = datetime.fromtimestamp(expire_after -
                                                    self.buffer_time)
        return package.url

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
