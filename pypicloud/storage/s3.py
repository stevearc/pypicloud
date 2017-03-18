""" Store packages in S3 """
import posixpath
from binascii import hexlify

import boto3
import logging
import rsa
from botocore.config import Config
from botocore.signers import CloudFrontSigner
from botocore.exceptions import ClientError
from contextlib import contextmanager
from datetime import datetime, timedelta
from hashlib import md5
from pyramid.httpexceptions import HTTPFound
from pyramid.settings import asbool
from six.moves.urllib.parse import quote  # pylint: disable=F0401,E0611
from six.moves.urllib.request import urlopen  # pylint: disable=F0401,E0611

from .base import IStorage
from pypicloud.models import Package
from pypicloud.util import parse_filename, getdefaults


LOG = logging.getLogger(__name__)


class S3Storage(IStorage):

    """ Storage backend that uses S3 """
    test = False

    def __init__(self, request=None, bucket=None, expire_after=None,
                 bucket_prefix=None, prepend_hash=None, redirect_urls=None,
                 sse=None,
                 **kwargs):
        super(S3Storage, self).__init__(request, **kwargs)
        self.bucket = bucket
        self.expire_after = expire_after
        self.bucket_prefix = bucket_prefix
        self.prepend_hash = prepend_hash
        self.redirect_urls = redirect_urls
        self.sse = sse

    @classmethod
    def configure(cls, settings):
        kwargs = super(S3Storage, cls).configure(settings)
        kwargs['expire_after'] = int(settings.get('storage.expire_after',
                                                  60 * 60 * 24))
        kwargs['bucket_prefix'] = settings.get('storage.prefix', '')
        kwargs['prepend_hash'] = asbool(settings.get('storage.prepend_hash',
                                                     True))
        access_key = settings.get('storage.access_key')
        secret_key = settings.get('storage.secret_key')
        region = settings.get('storage.region')
        signature_version = settings.get('storage.signature_version')
        user_agent = settings.get('storage.user_agent')
        user_agent_extra = settings.get('storage.user_agent_extra')
        use_accelerate_endpoint = \
            settings.get('storage.use_accelerate_endpoint', False)
        payload_signing_enabled = \
            settings.get('storage.payload_signing_enabled', False)
        addressing_style = settings.get('storage.addressing_style', 'auto')
        endpoint_url = getdefaults(settings, 'storage.endpoint_url',
                                   'storage.host', None)
        use_ssl = getdefaults(settings, 'storage.use_ssl', 'storage.is_secure',
                              True)
        verify = settings.get('storage.verify')
        kwargs['sse'] = sse = settings.get('storage.server_side_encryption')
        if sse not in [None, 'AES256', 'aws:kms']:
            LOG.warn("Unrecognized value %r for 'storage.sse'. See "
                     "https://boto3.readthedocs.io/en/latest/reference/services/s3.html#S3.Object.put "
                     "for more details", sse)
        kwargs['redirect_urls'] = asbool(settings.get('storage.redirect_urls',
                                                      False))

        config = Config(
            region_name=region,
            signature_version=signature_version,
            user_agent=user_agent,
            user_agent_extra=user_agent_extra,
            s3={
                'use_accelerate_endpoint': use_accelerate_endpoint,
                'payload_signing_enabled': payload_signing_enabled,
                'addressing_style': addressing_style,
            },
        )
        s3conn = boto3.resource(
            's3', region_name=region, use_ssl=use_ssl, verify=verify,
            endpoint_url=endpoint_url, aws_access_key_id=access_key,
            aws_secret_access_key=secret_key, config=config
        )

        bucket_name = settings.get('storage.bucket')
        if bucket_name is None:
            raise ValueError("You must specify the 'storage.bucket'")
        bucket = s3conn.Bucket(bucket_name)
        try:
            bucket.load()
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                LOG.info("Creating S3 bucket %s", bucket_name)
                bucket.create()
                bucket.wait_until_exists()
            else:
                if e.response['Error']['Code'] == '301':
                    LOG.warn("Bucket found in different region. Check that "
                             "the S3 bucket specified in 'storage.bucket' is "
                             "in 'storage.region'")
                raise
        kwargs['bucket'] = bucket
        return kwargs

    def calculate_path(self, package):
        """ Calculates the path of a package """
        path = package.name + '/' + package.filename
        if self.prepend_hash:
            m = md5()
            m.update(package.filename.encode('utf-8'))
            prefix = hexlify(m.digest()).decode('utf-8')[:4]
            path = prefix + '/' + path
        return path

    def get_path(self, package):
        """ Get the fully-qualified bucket path for a package """
        if 'path' not in package.data:
            filename = self.calculate_path(package)
            package.data['path'] = self.bucket_prefix + filename
        return package.data['path']

    def list(self, factory=Package):
        keys = self.bucket.objects.filter(Prefix=self.bucket_prefix)
        for summary in keys:
            # ObjectSummary has no metadata, so we have to fetch it.
            obj = summary.Object()
            filename = posixpath.basename(obj.key)
            name = obj.metadata.get('name')
            version = obj.metadata.get('version')
            summary = obj.metadata.get('summary')

            # We used to not store metadata. This is for backwards
            # compatibility
            if name is None or version is None:
                try:
                    name, version = parse_filename(filename)
                except ValueError:
                    LOG.warning("S3 file %s has no package name", obj.key)
                    continue

            pkg = factory(name, version, filename, obj.last_modified, summary,
                          path=obj.key)

            yield pkg

    def _generate_url(self, package):
        """ Generate a signed url to the S3 file """
        return self.bucket.meta.client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': self.bucket.name,
                'Key': self.get_path(package),
            },
            ExpiresIn=self.expire_after,
        )

    def get_url(self, package):
        if self.redirect_urls:
            return super(S3Storage, self).get_url(package)
        else:
            return self._generate_url(package)

    def download_response(self, package):
        return HTTPFound(location=self._generate_url(package))

    def upload(self, package, datastream):
        key = self.bucket.Object(self.get_path(package))
        kwargs = {}
        if self.sse is not None:
            kwargs['ServerSideEncryption'] = self.sse
        metadata = {
            'name': package.name,
            'version': package.version,
        }
        if package.summary:
            metadata['summary'] = package.summary
        key.put(Metadata=metadata, Body=datastream, **kwargs)

    def delete(self, package):
        self.bucket.delete_objects(Delete={
            'Objects': [
                {
                    'Key': self.get_path(package),
                }
            ]
        })

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
    def __init__(self, request=None, domain=None, private_key=None,
                 key_id=None, **kwargs):
        super(CloudFrontS3Storage, self).__init__(request, **kwargs)
        self.domain = domain
        self.private_key = private_key
        self.key_id = key_id
        self.private_key = private_key

        self.cf_signer = None
        if key_id is not None:
            self.cf_signer = CloudFrontSigner(self.key_id, self._rsa_signer)

        self.client = boto3.client('cloudfront')

    @classmethod
    def configure(cls, settings):
        kwargs = super(CloudFrontS3Storage, cls).configure(settings)
        kwargs['domain'] = settings['storage.cloud_front_domain']
        kwargs['key_id'] = settings.get('storage.cloud_front_key_id')
        private_key = settings.get('storage.cloud_front_key_string')
        if private_key is None:
            key_file = settings.get('storage.cloud_front_key_file')
            if key_file:
                with open(key_file, 'r') as ifile:
                    private_key = ifile.read()
        kwargs['private_key'] = private_key

        return kwargs

    def _rsa_signer(self, message):
        """ Generate a RSA signature for a message """
        return rsa.sign(
            message,
            rsa.PrivateKey.load_pkcs1(self.private_key.encode('utf8')),
            'SHA-1')  # CloudFront requires SHA-1 hash

    def _generate_url(self, package):
        """ Get the fully-qualified CloudFront path for a package """
        path = self.get_path(package)
        url = self.domain + '/' + quote(path)

        # No key id, no signer, so we don't have to sign the URL
        if self.cf_signer is None:
            return url

        # To sign with a canned policy:
        expires = datetime.utcnow() + timedelta(seconds=self.expire_after)
        return self.cf_signer.generate_presigned_url(
            url, date_less_than=expires)
