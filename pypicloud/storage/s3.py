""" Store packages in S3 """
import calendar
import logging
import posixpath
import time
from contextlib import contextmanager
from hashlib import md5
from urllib import urlopen, quote

import boto.s3
from boto.cloudfront import Distribution
from boto.s3.key import Key
import boto.s3.connection
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


class S3Storage(IStorage):

    """ Storage backend that uses S3 """
    test = False

    def __init__(self, request=None, bucket=None, expire_after=None,
                 bucket_prefix=None, prepend_hash=None, redirect_urls=None,
                 **kwargs):
        super(S3Storage, self).__init__(request, **kwargs)
        self.bucket = bucket
        self.expire_after = expire_after
        self.bucket_prefix = bucket_prefix
        self.prepend_hash = prepend_hash
        self.redirect_urls = redirect_urls

    @classmethod
    def configure(cls, settings):
        kwargs = super(S3Storage, cls).configure(settings)
        kwargs['expire_after'] = int(getdefaults(
            settings, 'storage.expire_after', 'aws.expire_after', 60 * 60 *
            24))
        kwargs['bucket_prefix'] = getdefaults(
            settings, 'storage.prefix', 'aws.prefix', '')
        kwargs['prepend_hash'] = asbool(getdefaults(
            settings, 'storage.prepend_hash', 'aws.prepend_hash', True))
        access_key = getdefaults(settings, 'storage.access_key',
                                 'aws.access_key', None)
        secret_key = getdefaults(settings, 'storage.secret_key',
                                 'aws.secret_key', None)
        host = getdefaults(settings, 'storage.host',
                           'aws.host', boto.s3.connection.NoHostProvided)
        is_secure = getdefaults(settings, 'storage.is_secure',
                                'aws.is_secure', True)
        calling_format = settings.get('storage.calling_format',
                                      'SubdomainCallingFormat')
        kwargs['redirect_urls'] = asbool(settings.get('storage.redirect_urls',
                                                      False))

        if calling_format not in SUPPORTED_CALLING_FORMATS:
            raise ValueError("Only {0} are supported for calling_format"
                             .format(', '.join(SUPPORTED_CALLING_FORMATS)))

        # We used to always use boto.connect_s3 because it can look up buckets
        # in any region. New regions require AWS4-HMAC-SHA256, which boto can
        # only do with a region connection. So if the region is specified (and
        # it must be for new regions like eu-central-1), use a region
        # connection.
        location = settings.get('storage.region')
        if location is None:
            s3conn = boto.connect_s3(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                host=host,
                is_secure=asbool(is_secure),
                calling_format=SUPPORTED_CALLING_FORMATS[calling_format]())
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

    def _generate_url(self, package):
        """ Generate a signed url to the S3 file """
        key = Key(self.bucket, self.get_path(package))
        return key.generate_url(self.expire_after)

    def get_url(self, package):
        if self.redirect_urls:
            return super(S3Storage, self).get_url(package)
        else:
            return self._generate_url(package)

    def download_response(self, package):
        return HTTPFound(location=self._generate_url(package))

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
        url = self._generate_url(package)
        handle = urlopen(url)
        try:
            yield handle
        finally:
            handle.close()


class CloudFrontS3Storage(S3Storage):

    """ Storage backend that uses S3 and CloudFront """
    def __init__(self, request=None, bucket=None, expire_after=None, bucket_prefix=None,
                 prepend_hash=None, cloud_front_domain=None, cloud_front_key_file=None,
                 cloud_front_key_string=None, cloud_front_key_id=None, **kwargs):
        super(CloudFrontS3Storage, self).__init__(request, bucket, expire_after, bucket_prefix, prepend_hash, **kwargs)
        self.cloud_front_domain = cloud_front_domain
        self.cloud_front_key_file = cloud_front_key_file
        self.cloud_front_key_id = cloud_front_key_id
        self.cloud_front_key_string = cloud_front_key_string

        self.distribution = Distribution()

    @classmethod
    def configure(cls, settings):
        kwargs = super(CloudFrontS3Storage, cls).configure(settings)
        kwargs['cloud_front_domain'] = getdefaults(
            settings, 'storage.cloud_front_domain', 'aws.cloud_front_domain', '')
        kwargs['cloud_front_key_file'] = getdefaults(
            settings, 'storage.cloud_front_key_file', 'aws.cloud_front_key_file', None)
        kwargs['cloud_front_key_string'] = getdefaults(
            settings, 'storage.cloud_front_key_string', 'aws.cloud_front_key_string', None)
        kwargs['cloud_front_key_id'] = getdefaults(
            settings, 'storage.cloud_front_key_id', 'aws.cloud_front_key_id', '')

        return kwargs

    def _generate_url(self, package):
        """ Get the fully-qualified CloudFront path for a package """
        path = self.calculate_path(package)
        url = self.cloud_front_domain + '/' + quote(path)

        if self.cloud_front_key_file or self.cloud_front_key_string:
            expire_time = int(time.time() + self.expire_after)
            url = self.distribution.create_signed_url(
                url, self.cloud_front_key_id, expire_time, private_key_file=self.cloud_front_key_file,
                private_key_string=self.cloud_front_key_string)

        return url
