""" Store packages in S3 """
import logging
import posixpath
from datetime import timedelta
from urllib.parse import quote, urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from botocore.signers import CloudFrontSigner
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from pyramid.settings import asbool, falsey
from pyramid_duh.settings import asdict
from smart_open import open as _open

from pypicloud.dateutil import utcnow
from pypicloud.models import Package
from pypicloud.util import (
    PackageParseError,
    normalize_metadata,
    parse_filename,
    stream_file,
)

from .object_store import ObjectStoreStorage

LOG = logging.getLogger(__name__)


class S3Storage(ObjectStoreStorage):

    """Storage backend that uses S3 and support running on EC2 instances with instance profiles.

    bucket_name is not really optional here, but we have to treat it as optional unless
    we can validate that request isn't actually optional here either, or risk changing argument order.
    """

    test = False

    def __init__(
        self, request=None, bucket_name=None, storage_config=None, resource_config=None, **kwargs
    ):
        super(S3Storage, self).__init__(request=request, **kwargs)
        self.bucket_name = bucket_name if bucket_name is not None else ""
        self.storage_config = storage_config if storage_config is not None else {}
        self.resource_config = resource_config if resource_config is not None else {}
        self._bucket = None

    @classmethod
    def _subclass_specific_config(cls, settings, common_config):
        sse = settings.get("storage.server_side_encryption")
        if sse not in [None, "AES256", "aws:kms"]:
            LOG.warning(
                "Unrecognized value %r for 'storage.sse'. See "
                "https://boto3.readthedocs.io/en/latest/reference/services/s3.html#S3.Object.put "
                "for more details",
                sse,
            )

        bucket_name = settings.get("storage.bucket")
        if bucket_name is None:
            raise ValueError("You must specify the 'storage.bucket'")

        config_settings = settings.get_as_dict(
            "storage.",
            region_name=str,
            signature_version=str,
            user_agent=str,
            user_agent_extra=str,
            connect_timeout=int,
            read_timeout=int,
            parameter_validation=asbool,
            max_pool_connections=int,
            proxies=asdict,
        )
        config_settings["s3"] = settings.get_as_dict(
            "storage.",
            use_accelerate_endpoint=asbool,
            payload_signing_enabled=asbool,
            addressing_style=str,
            signature_version=str,
        )

        config = Config(**config_settings)

        def verify_value(val):
            """Verify can be a boolean (False) or a string"""
            s = str(val).strip().lower()
            if s in falsey:
                return False
            else:
                return str(val)

        resource_config = settings.get_as_dict(
            "storage.",
            region_name=str,
            api_version=str,
            use_ssl=asbool,
            verify=verify_value,
            endpoint_url=str,
            aws_access_key_id=str,
            aws_secret_access_key=str,
            aws_session_token=str,
        )

        return {
            "sse": sse,
            "bucket_name": bucket_name,
            "storage_config": config,
            "resource_config": resource_config,
        }

    def create_bucket_if_not_exist(self):

        s3Resource = boto3.resource("s3", config=self.storage_config, **self.resource_config)

        bucket = s3Resource.Bucket(self.bucket_name)
        try:
            s3Resource.meta.client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                LOG.info("Creating S3 bucket %s", self.bucket_name)

                if self.region_name and self.region_name != "us-east-1":
                    location = {"LocationConstraint": self.region_name}
                    bucket.create(CreateBucketConfiguration=location)
                else:
                    bucket.create()

                bucket.wait_until_exists()
            else:
                if e.response["Error"]["Code"] == "301":
                    LOG.error(
                        "Bucket found in different region. Check that "
                        "the S3 bucket specified in 'storage.bucket' is "
                        "in 'storage.region_name'"
                    )
                raise
        return bucket

    @classmethod
    def package_from_object(cls, obj, factory):
        """Create a package from a S3 object"""
        filename = posixpath.basename(obj.key)
        name = obj.metadata.get("name")
        version = obj.metadata.get("version")
        metadata = Package.read_metadata(obj.metadata)
        # We used to not store metadata. This is for backwards
        # compatibility
        if name is None or version is None:
            try:
                name, version = parse_filename(filename)
            except PackageParseError:
                LOG.warning("S3 file %s has no package name", obj.key)
                return None

        return factory(name, version, filename, obj.last_modified, path=obj.key, **metadata)

    @property
    def bucket(self):
        """Dynamically creates boto3.s3.Bucket resource to ensure automatically refreshing credentials work.

        Taking this approach allows for the credentials to be rotated if they need to be.
        E.g. when deployed to an EC2 instance using an instance profile.
        boto3 will handle updating the credentials automatically, but the resource itself can't be kept alive forever, else subsequent calls
        result in expired credentials errors.

        Separating create_bucket_if_not_exists here from get_bucket to avoid unnecessary increase in bucket.head calls
        that would be introduced by implementing self.bucket as a property.
        """
        if self._bucket is None:
            self._bucket = self.create_bucket_if_not_exist()
        else:
            s3Resource = boto3.resource("s3", config=self.storage_config, **self.resource_config)
            self._bucket = s3Resource.Bucket(self.bucket_name)
        return self._bucket

    def list(self, factory=Package):
        keys = self.bucket.objects.filter(Prefix=self.bucket_prefix)
        for summary in keys:
            # ObjectSummary has no metadata, so we have to fetch it.
            obj = summary.Object()
            pkg = self.package_from_object(obj, factory)
            if pkg is not None:
                yield pkg

    def _generate_url(self, package):
        """Generate a signed url to the S3 file


        ? question: Does this implementation work if someone is specifying an endpoint_url?
        """
        if self.public_url:
            if self.region_name:
                return "https://s3.{0}.amazonaws.com/{1}/{2}".format(
                    self.region_name, self.bucket_name, self.get_path(package)
                )
            else:
                if "." in self.bucket_name:
                    self._log_region_warning()
                return "https://{0}.s3.amazonaws.com/{1}".format(
                    self.bucket_name, self.get_path(package)
                )
        url = self.bucket.meta.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket_name, "Key": self.get_path(package)},
            ExpiresIn=self.expire_after,
        )
        # There is a special case if your bucket has a '.' in the name. The
        # generated URL will return a 301 and the pip downloads will fail.
        # If you provide a region_name, boto should correctly generate a url in
        # the form of `s3.<region>.amazonaws.com`
        # See https://github.com/stevearc/pypicloud/issues/145
        if "." in self.bucket_name:
            pieces = urlparse(url)
            if pieces.netloc == "s3.amazonaws.com" and self.region_name is None:
                self._log_region_warning()
        return url

    def _log_region_warning(self):
        """Spit out a warning about including region_name"""
        LOG.warning(
            "Your signed S3 urls may not work! "
            "Try adding the bucket region to the config with "
            "'storage.region_name = <region>' or using a bucket "
            "without any dots ('.') in the name."
        )

    def get_uri(self, package):
        return f"s3://{self.bucket_name}/{self.get_path(package)}"

    def upload(self, package, datastream):
        kwargs = {}
        if self.sse is not None:
            kwargs["ServerSideEncryption"] = self.sse
        if self.object_acl:
            kwargs["ACL"] = self.object_acl
        if self.storage_class is not None:
            kwargs["StorageClass"] = self.storage_class
        metadata = package.get_metadata()
        metadata["name"] = package.name
        metadata["version"] = package.version
        metadata = normalize_metadata(metadata)
        kwargs["Metadata"] = metadata

        with _open(
            self.get_uri(package),
            "wb",
            compression="disable",
            transport_params={
                "client": self.bucket.meta.client,
                "client_kwargs": {"S3.Client.create_multipart_upload": kwargs},
            },
        ) as fp:
            for chunk in stream_file(datastream):
                fp.write(chunk)  # multipart upload

    def open(self, package):
        """Overwrite open method to re-use client instead of using signed url."""
        return _open(
            self.get_uri(package),
            "rb",
            compression="disable",
            transport_params={"client": self.bucket.meta.client},
        )

    def delete(self, package):
        self.bucket.delete_objects(Delete={"Objects": [{"Key": self.get_path(package)}]})

    def check_health(self):
        """Check the health.

        suggestion:
            When deployed in environments that repeatedly hit the pypicloud server for health checks,
            the below might not be very useful?
            The bucket will exist and we will have access to it due to calling head_bucket much earlier during initialization.
            Doing so repeatedly (every 5-10 seconds, etc) increases AWS api costs and seemingly provides little actual value.

            In line with this suggestion, updating this to just always return True, "" for now.
            I suppose an argument could be made that this validates our connectivity to AWS, but if that is failing we won't need this health check to tell us that...
        Returns:
        """

        return True, ""


class CloudFrontS3Storage(S3Storage):

    """Storage backend that uses S3 and CloudFront"""

    def __init__(self, request=None, domain=None, crypto_pk=None, key_id=None, **kwargs):
        super(CloudFrontS3Storage, self).__init__(request, **kwargs)
        self.domain = domain
        self.crypto_pk = crypto_pk
        self.key_id = key_id

        self.cf_signer = None
        if key_id is not None:
            self.cf_signer = CloudFrontSigner(self.key_id, self._rsa_signer)

        self.client = boto3.client("cloudfront")

    @classmethod
    def configure(cls, settings):
        kwargs = super(CloudFrontS3Storage, cls).configure(settings)
        kwargs["domain"] = settings["storage.cloud_front_domain"]
        kwargs["key_id"] = settings.get("storage.cloud_front_key_id")
        private_key = settings.get("storage.cloud_front_key_string")
        if private_key is None:
            key_file = settings.get("storage.cloud_front_key_file")
            if key_file:
                with open(key_file, "rb") as ifile:
                    private_key = ifile.read()
        else:
            private_key = private_key.encode("utf-8")
        crypto_pk = serialization.load_pem_private_key(
            private_key, password=None, backend=default_backend()
        )
        kwargs["crypto_pk"] = crypto_pk

        return kwargs

    def _rsa_signer(self, message):
        """Generate a RSA signature for a message"""
        return self.crypto_pk.sign(message, padding.PKCS1v15(), hashes.SHA1())

    def _generate_url(self, package):
        """Get the fully-qualified CloudFront path for a package"""
        path = self.get_path(package)
        url = self.domain + "/" + quote(path)

        # No key id, no signer, so we don't have to sign the URL
        if self.cf_signer is None:
            return url

        # To sign with a canned policy:
        expires = utcnow() + timedelta(seconds=self.expire_after)
        return self.cf_signer.generate_presigned_url(url, date_less_than=expires)
