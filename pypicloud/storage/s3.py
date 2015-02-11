""" Store packages in S3 """
import calendar
import logging
import posixpath
import time
from contextlib import contextmanager
from hashlib import md5
from urllib import urlopen

import boto.s3
from boto.s3.key import Key
from pyramid.httpexceptions import HTTPNotFound
from pyramid.settings import asbool

from .base import IStorage
from pypicloud.models import Package
from pypicloud.util import parse_filename, getdefaults


LOG = logging.getLogger(__name__)


class S3Storage(IStorage):

    """ Storage backend that uses S3 """
    test = False

    def __init__(self, request=None, bucket=None, expire_after=None,
                 buffer_time=None, bucket_prefix=None, prepend_hash=None,
                 **kwargs):
        super(S3Storage, self).__init__(request, **kwargs)
        self.bucket = bucket
        self.expire_after = expire_after
        self.buffer_time = buffer_time
        self.bucket_prefix = bucket_prefix
        self.prepend_hash = prepend_hash

    @classmethod
    def configure(cls, settings):
        kwargs = super(S3Storage, cls).configure(settings)
        kwargs['expire_after'] = int(getdefaults(
            settings, 'storage.expire_after', 'aws.expire_after', 60 * 60 *
            24))
        kwargs['buffer_time'] = int(getdefaults(
            settings, 'storage.buffer_time', 'aws.buffer_time', 600))
        kwargs['bucket_prefix'] = getdefaults(
            settings, 'storage.prefix', 'aws.prefix', '')
        kwargs['prepend_hash'] = asbool(getdefaults(
            settings, 'storage.prepend_hash', 'aws.prepend_hash', True))
        access_key = getdefaults(settings, 'storage.access_key',
                                 'aws.access_key', None)
        secret_key = getdefaults(settings, 'storage.secret_key',
                                 'aws.secret_key', None)

        # We used to always use boto.connect_s3 because it can look up buckets
        # in any region. New regions require AWS4-HMAC-SHA256, which boto can
        # only do with a region connection. So if the region is specified (and
        # it must be for new regions like eu-central-1), use a region
        # connection.
        location = settings.get('storage.region')
        if location is None:
            s3conn = boto.connect_s3(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key)
        else:
            s3conn = boto.s3.connect_to_region(location,
                                               aws_access_key_id=access_key,
                                               aws_secret_access_key=secret_key)
        aws_bucket = getdefaults(settings, 'storage.bucket', 'aws.bucket',
                                 None)
        if aws_bucket is None:
            raise ValueError("You must specify the 'storage.bucket'")
        try:
            bucket = s3conn.get_bucket(aws_bucket)
        except boto.exception.S3ResponseError as e:
            if e.error_code != 'NoSuchBucket':
                if e.status == 301:
                    LOG.warn("Bucket found in different region. Check that "
                             "the S3 bucket specified in 'storage.bucket' is "
                             "in 'storage.region'")
                raise
            location = getdefaults(settings, 'storage.region', 'aws.region',
                                   boto.s3.connection.Location.DEFAULT)
            LOG.info("Creating S3 bucket %s in region %s", aws_bucket,
                     location)
            bucket = s3conn.create_bucket(aws_bucket, location=location)
        kwargs['bucket'] = bucket
        return kwargs

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
            expire_after = self.expire_after
            buffer_time = self.buffer_time

            # This is a bit of a hack. If we are using session-based
            # credentials, those might expire before the URL. We will need to
            # adjust the expire_after and buffer_time accordingly.
            # See issue: https://github.com/mathcamp/pypicloud/issues/38
            credential_expr = getattr(self.bucket.connection.provider,
                                      '_credential_expiry_time', None)
            if credential_expr is not None:
                seconds = calendar.timegm(credential_expr.utctimetuple())
                if seconds < expire_after:
                    # More hacks: boto refreshes session tokens 5 minutes
                    # before expiration, so we have to refresh url after that.
                    buffer_time = 4 * 60
                    expire_after = seconds

            expire_time = time.time() + expire_after
            url = key.generate_url(expire_time, expires_in_absolute=True)
            package.data['url'] = url
            expire = expire_time - buffer_time
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
        # S3 doesn't support uploading from a non-file stream, so we have to
        # read it into memory :(
        key.set_contents_from_string(data.read())

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
