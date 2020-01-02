# -*- coding: utf-8 -*-
""" Tests for package storage backends """
import json
import time
import datetime
from six import BytesIO

import shutil
import tempfile
from mock import MagicMock, patch, ANY
from moto import mock_s3
from six.moves.urllib.parse import urlparse, parse_qs  # pylint: disable=F0401,E0611

import boto3
import os
import re
from botocore.exceptions import ClientError
from pypicloud.models import Package
from pypicloud.storage import (
    S3Storage,
    CloudFrontS3Storage,
    FileStorage,
    GoogleCloudStorage,
)
from . import make_package

try:
    import unittest2 as unittest  # pylint: disable=F0401
except ImportError:
    import unittest


class TestS3Storage(unittest.TestCase):

    """ Tests for storing packages in S3 """

    def setUp(self):
        super(TestS3Storage, self).setUp()
        self.s3_mock = mock_s3()
        self.s3_mock.start()
        self.settings = {
            "storage.bucket": "mybucket",
            "storage.aws_access_key_id": "abc",
            "storage.aws_secret_access_key": "bcd",
        }
        self.s3 = boto3.resource("s3")
        self.bucket = self.s3.create_bucket(Bucket="mybucket")
        patch.object(S3Storage, "test", True).start()
        kwargs = S3Storage.configure(self.settings)
        self.storage = S3Storage(MagicMock(), **kwargs)

    def tearDown(self):
        super(TestS3Storage, self).tearDown()
        patch.stopall()
        self.s3_mock.stop()

    def test_list(self):
        """ Can construct a package from a S3 Key """
        name, version, filename, summary = "mypkg", "1.2", "pkg.tar.gz", "text"
        key = self.bucket.Object(name + "/" + filename)
        key.put(
            Metadata={"name": name, "version": version, "summary": summary},
            Body="foobar",
        )
        package = list(self.storage.list(Package))[0]
        self.assertEqual(package.name, name)
        self.assertEqual(package.version, version)
        self.assertEqual(package.filename, filename)
        self.assertEqual(package.summary, summary)

    def test_list_no_metadata(self):
        """ Test that list works on old keys with no metadata """
        name, version = "mypkg", "1.2"
        filename = "%s-%s.tar.gz" % (name, version)
        key = self.bucket.Object(name + "/" + filename)
        key.put(Body="foobar")
        package = list(self.storage.list(Package))[0]
        self.assertEqual(package.name, name)
        self.assertEqual(package.version, version)
        self.assertEqual(package.filename, filename)
        self.assertEqual(package.summary, None)

    def test_get_url(self):
        """ Mock s3 and test package url generation """
        package = make_package()
        response = self.storage.download_response(package)

        parts = urlparse(response.location)
        self.assertEqual(parts.scheme, "https")
        self.assertEqual(parts.hostname, "mybucket.s3.amazonaws.com")
        self.assertEqual(parts.path, "/" + self.storage.get_path(package))
        query = parse_qs(parts.query)
        self.assertItemsEqual(query.keys(), ["Expires", "Signature", "AWSAccessKeyId"])
        self.assertTrue(int(query["Expires"][0]) > time.time())
        self.assertEqual(
            query["AWSAccessKeyId"][0], self.settings["storage.aws_access_key_id"]
        )

    def test_delete(self):
        """ delete() should remove package from storage """
        package = make_package()
        self.storage.upload(package, BytesIO())
        self.storage.delete(package)
        keys = list(self.bucket.objects.all())
        self.assertEqual(len(keys), 0)

    def test_upload(self):
        """ Uploading package sets metadata and sends to S3 """
        package = make_package()
        datastr = b"foobar"
        data = BytesIO(datastr)
        self.storage.upload(package, data)
        key = list(self.bucket.objects.all())[0].Object()
        contents = BytesIO()
        key.download_fileobj(contents)
        self.assertEqual(contents.getvalue(), datastr)
        self.assertEqual(key.metadata["name"], package.name)
        self.assertEqual(key.metadata["version"], package.version)
        self.assertEqual(key.metadata["summary"], package.summary)

    def test_upload_prepend_hash(self):
        """ If prepend_hash = True, attach a hash to the file path """
        self.storage.prepend_hash = True
        package = make_package()
        data = BytesIO()
        self.storage.upload(package, data)
        key = list(self.bucket.objects.all())[0]

        pattern = r"^[0-9a-f]{4}/%s/%s$" % (
            re.escape(package.name),
            re.escape(package.filename),
        )
        match = re.match(pattern, key.key)
        self.assertIsNotNone(match)

    def test_create_bucket_eu(self):
        """ If S3 bucket doesn't exist, create it """
        settings = {
            "storage.bucket": "new_bucket",
            "storage.region_name": "eu-central-1",
            "signature_version": "s3v4",
        }
        S3Storage.configure(settings)

        bucket = self.s3.Bucket("new_bucket")
        bucket.load()

    def test_create_bucket_us(self):
        """ If S3 bucket doesn't exist, create it """
        settings = {"storage.bucket": "new_bucket", "storage.region_name": "us-west-1"}
        S3Storage.configure(settings)

        bucket = self.s3.Bucket("new_bucket")
        bucket.load()

    def test_object_acl(self):
        """ Can specify an object ACL for S3 objects """
        settings = dict(self.settings)
        settings["storage.object_acl"] = "authenticated-read"
        kwargs = S3Storage.configure(settings)
        storage = S3Storage(MagicMock(), **kwargs)
        package = make_package()
        storage.upload(package, BytesIO())
        acl = list(self.bucket.objects.all())[0].Object().Acl()
        self.assertItemsEqual(
            acl.grants,
            [
                {
                    "Grantee": {"Type": "CanonicalUser", "ID": ANY},
                    "Permission": "FULL_CONTROL",
                },
                {
                    "Grantee": {
                        "Type": "Group",
                        "URI": "http://acs.amazonaws.com/groups/global/AuthenticatedUsers",
                    },
                    "Permission": "READ",
                },
            ],
        )

    def test_storage_class(self):
        """ Can specify a storage class for S3 objects """
        settings = dict(self.settings)
        settings["storage.storage_class"] = "STANDARD_IA"
        kwargs = S3Storage.configure(settings)
        storage = S3Storage(MagicMock(), **kwargs)
        package = make_package()
        storage.upload(package, BytesIO())
        storage_class = list(self.bucket.objects.all())[0].Object().storage_class
        self.assertItemsEqual(storage_class, "STANDARD_IA")

    def test_check_health_success(self):
        """ check_health returns True for good connection """
        ok, msg = self.storage.check_health()
        self.assertTrue(ok)

    def test_check_health_fail(self):
        """ check_health returns False for bad connection """
        dbmock = self.storage.bucket.meta.client = MagicMock()

        def throw(*_, **__):
            """ Throw an exception """
            raise ClientError({"Error": {}}, "OP")

        dbmock.head_bucket.side_effect = throw
        ok, msg = self.storage.check_health()
        self.assertFalse(ok)

    def test_unicode_summary(self):
        """ Unicode characters in summary will be converted to ascii """
        package = make_package(summary="text 🤪")
        datastr = b"foobar"
        data = BytesIO(datastr)
        self.storage.upload(package, data)
        key = list(self.bucket.objects.all())[0].Object()
        contents = BytesIO()
        key.download_fileobj(contents)
        self.assertEqual(contents.getvalue(), datastr)
        self.assertEqual(key.metadata["name"], package.name)
        self.assertEqual(key.metadata["version"], package.version)
        self.assertEqual(key.metadata["summary"], "text ")


class TestCloudFrontS3Storage(unittest.TestCase):

    """ Tests for storing packages on S3 with CloudFront in front """

    def setUp(self):
        super(TestCloudFrontS3Storage, self).setUp()
        self.s3_mock = mock_s3()
        self.s3_mock.start()
        self.settings = {
            "storage.bucket": "mybucket",
            "storage.aws_access_key_id": "abc",
            "storage.aws_secret_access_key": "bcd",
            "storage.cloud_front_domain": "https://abcdef.cloudfront.net",
            "storage.cloud_front_key_file": "",
            "storage.cloud_front_key_string": "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIICXQIBAAKBgQDNBN3WHzIgmOEkBVNdBlTR7iGYyUXDVuFRkJlYp/n1/EZf2YtE\n"
            "BpxJAgqdwej8beWV16QXOnKXQpsGAeu7x2pvOGFyRGytmLDeUXayfIF/E46w83V2\n"
            "r53NOBrlezagqCAz9uafocyNaXlxZfp4tx82sEmpSmHGwd//+n6zgXNC0QIDAQAB\n"
            "AoGAd5EIA1GMPYCLhSNp+82ueARGKcHwYrzviU8ob5D/cVtge5P26YRlbxq2sEyf\n"
            "oWBCTgJGW5mlrNuWZ4mFPq1NP2X2IU80k/J67KOuOelAykIVQw6q6GAjtmh40x4N\n"
            "EekoFzxVqoFKqWOJ1UNP0jNOyfzxU5dfzvw5GOEXob9usjECQQD3++wWCoq+YRCz\n"
            "8qqav2M7leoAnDwmCYKpnugDU0NR61sZADS3kJHnhXAbPFQI4dRfETJOkKE/iDph\n"
            "G0Rtdfm1AkEA06VoI49wjEMYs4ah3qwpvhuVyxVa9iozIEoDYiVCOOBZw8rX79G4\n"
            "+5yzC9ehy9ugWttSA2jigNXVB6ORN3+mLQJBAM47lZizBbXUdZahvp5ZgoZgY65E\n"
            "QIWFrUOxYtS5Hyh2qlk9YZozwhOgVp5f6qdEYGD7pTHPeDqk6aAulBbQYW0CQQC4\n"
            "hAw2dGd64UQ3v7h/mTkLNKFzXDrhQgkwrVYlyrXhQDcCK2X2/rB3LDYsrOGyCNfU\n"
            "XkEyF87g44vGDSQdbnxBAkA1Y+lB/pqdyHMv5RFabkBvU0yQDfekAKHeQ6rS+21g\n"
            "dWedUVc1JNnKtb8W/rMfdjg9YLYqUTvoBvp0DjfwdYc4\n"
            "-----END RSA PRIVATE KEY-----",
            "storage.cloud_front_key_id": "key-id",
        }
        s3 = boto3.resource("s3")
        self.bucket = s3.create_bucket(Bucket="mybucket")
        patch.object(CloudFrontS3Storage, "test", True).start()
        kwargs = CloudFrontS3Storage.configure(self.settings)
        self.storage = CloudFrontS3Storage(MagicMock(), **kwargs)

    def test_get_url(self):
        """ Mock s3 and test package url generation """
        package = make_package(version="1.1+g12345")
        response = self.storage.download_response(package)

        parts = urlparse(response.location)
        self.assertEqual(parts.scheme, "https")
        self.assertEqual(parts.netloc, "abcdef.cloudfront.net")
        self.assertEqual(parts.path, "/bcc4/mypkg/mypkg-1.1%2Bg12345.tar.gz")
        query = parse_qs(parts.query)
        self.assertItemsEqual(query.keys(), ["Key-Pair-Id", "Expires", "Signature"])
        self.assertTrue(int(query["Expires"][0]) > time.time())
        self.assertEqual(
            query["Key-Pair-Id"][0], self.settings["storage.cloud_front_key_id"]
        )


class TestFileStorage(unittest.TestCase):

    """ Tests for storing packages as local files """

    def setUp(self):
        super(TestFileStorage, self).setUp()
        self.tempdir = tempfile.mkdtemp()
        settings = {"storage.dir": self.tempdir}
        kwargs = FileStorage.configure(settings)
        self.request = MagicMock()
        self.storage = FileStorage(self.request, **kwargs)

    def tearDown(self):
        super(TestFileStorage, self).tearDown()
        shutil.rmtree(self.tempdir)

    def test_upload(self):
        """ Uploading package saves file """
        package = make_package()
        datastr = b"foobar"
        data = BytesIO(datastr)
        self.storage.upload(package, data)
        filename = self.storage.get_path(package)
        self.assertTrue(os.path.exists(filename))
        with open(filename, "r") as ifile:
            self.assertEqual(ifile.read(), "foobar")
        meta_file = self.storage.get_metadata_path(package)
        self.assertTrue(os.path.exists(meta_file))
        with open(meta_file, "r") as mfile:
            self.assertEqual(json.loads(mfile.read()), {"summary": package.summary})

    def test_list(self):
        """ Can iterate over uploaded packages """
        package = make_package()
        path = self.storage.get_path(package)
        meta_file = self.storage.get_metadata_path(package)
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as ofile:
            ofile.write("foobar")

        with open(meta_file, "w") as mfile:
            mfile.write(json.dumps({"summary": package.summary}))

        pkg = list(self.storage.list(Package))[0]
        self.assertEqual(pkg.name, package.name)
        self.assertEqual(pkg.version, package.version)
        self.assertEqual(pkg.filename, package.filename)
        self.assertEqual(pkg.summary, package.summary)

    def test_delete(self):
        """ delete() should remove package from storage """
        package = make_package()
        path = self.storage.get_path(package)
        meta_path = self.storage.get_metadata_path(package)
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as ofile:
            ofile.write("foobar")
        with open(meta_path, "w") as mfile:
            mfile.write("foobar")
        self.storage.delete(package)
        self.assertFalse(os.path.exists(path))
        self.assertFalse(os.path.exists(meta_path))

    def test_create_package_dir(self):
        """ configure() will create the package dir if it doesn't exist """
        tempdir = tempfile.mkdtemp()
        os.rmdir(tempdir)
        settings = {"storage.dir": tempdir}
        FileStorage.configure(settings)
        try:
            self.assertTrue(os.path.exists(tempdir))
        finally:
            os.rmdir(tempdir)

    def test_check_health(self):
        """ Base check_health returns True """
        ok, msg = self.storage.check_health()
        self.assertTrue(ok)


class MockGCSBlob(object):
    """ Mock object representing the google.cloud.storage.Blob class """

    def __init__(self, name, bucket):
        self.name = name
        self.metadata = {}
        self.updated = None
        self._content = None
        self._acl = None
        self.bucket = bucket
        self.generate_signed_url = MagicMock(wraps=self._generate_signed_url)
        self.upload_from_file = MagicMock(wraps=self._upload_from_file)
        self.delete = MagicMock(wraps=self._delete)
        self.update_storage_class = MagicMock(wraps=self._update_storage_class)

    def upload_from_string(self, s):
        """ Utility method for uploading this blob; not used by the
            GoogleCloudStorage backend, but used to pre-populate the GCS
            mock for testing
        """
        self.updated = datetime.datetime.utcnow()
        self._content = s
        self.bucket._upload_blob(self)

    def _upload_from_file(self, fp, predefined_acl):
        """ Mock the upload_from_file() method on google.cloud.storage.Blob """
        self._acl = predefined_acl
        self.upload_from_string(fp.read())

    def _delete(self):
        """ Mock the delete() method on google.cloud.storage.Blob """
        self.bucket._delete_blob(self.name)

    def _generate_signed_url(self, expiration, credentials, version):
        """ Mock the generate_signed_url() method on
            google.cloud.storage.Blob
        """
        return "https://storage.googleapis.com/{bucket_name}/{blob_name}?Expires={expires}&GoogleAccessId=my-service-account%40my-project.iam.gserviceaccount.com&Signature=MySignature".format(
            bucket_name=self.bucket.name,
            blob_name=self.name,
            expires=int(time.time() + expiration.total_seconds()),
        )

    def _update_storage_class(self, storage_class):
        """ Mock the update_storage_class() method on google.cloud.storage.Blob.
            This is a NOOP because we only check to make sure that it was
            called, not that it changed any state on the MockGCSBlob class
        """


class MockGCSBucket(object):
    """ Mock object representing the google.cloud.storage.Bucket class """

    def __init__(self, name, client):
        self.name = name
        self.client = client

        self._created = False
        self.location = None

        self.blob = MagicMock(wraps=self._blob)
        self.list_blobs = MagicMock(wraps=self._list_blobs)
        self.exists = MagicMock(wraps=self._exists)
        self.create = MagicMock(wraps=self._create)

        self._blobs = {}

    def _upload_blob(self, blob):
        """ Method used by the MockGCSBlob class to register blobs after
            MockGCSBlob.upload is called
        """
        self._blobs[blob.name] = blob

    def _delete_blob(self, blob_name):
        """ Method used by the MockGCSBlob class to unregister blobs after
            MockGCSBlob.delete is called
        """
        self._blobs.pop(blob_name)

    def _blob(self, blob_name):
        """ Mock the blob() method on google.cloud.storage.Bucket """
        return MockGCSBlob(blob_name, self)

    def _list_blobs(self, prefix=None):
        """ Mock the list_blobs() method on google.cloud.storage.Bucket """
        return [
            item
            for item in self._blobs.values()
            if prefix is None or item.name.startswith(prefix)
        ]

    def _exists(self):
        """ Mock the exists() method on google.cloud.storage.Bucket """
        return self._created

    def _create(self):
        """ Mock the create() method on google.cloud.storage.Bucket """
        self._created = True


class MockGCSClient(object):
    """ Mock object representing the google.cloud.storage.Client class """

    def __init__(self):
        self.bucket = MagicMock(wraps=self._bucket)

        self._buckets = {}

    def from_service_account_json(self, *args, **kwargs):
        """ Mock the from_service_account_json method from the cloud storage
            client class, used by the GoogleCloudStorage backend.
        """
        return self

    def __call__(self):
        """ Provide a call() method so that we can easily patch an instance
            of this class in place of the constructor of the mocked class
        """
        return self

    def _bucket(self, bucket_name):
        """ Mock the bucket() method on google.cloud.storage.Bucket """
        if bucket_name not in self._buckets:
            self._buckets[bucket_name] = MockGCSBucket(bucket_name, self)

        return self._buckets[bucket_name]


class TestGoogleCloudStorage(unittest.TestCase):

    """ Tests for storing packages in GoogleCloud """

    def setUp(self):
        super(TestGoogleCloudStorage, self).setUp()
        self.gcs = MockGCSClient()
        patch("google.cloud.storage.Client", self.gcs).start()
        self.settings = {
            "storage.bucket": "mybucket",
            "storage.gcp_service_account_json_filename": "my-filename.json",
        }
        self.bucket = self.gcs.bucket("mybucket")
        self.bucket._created = True
        patch.object(GoogleCloudStorage, "test", True).start()
        kwargs = GoogleCloudStorage.configure(self.settings)
        self.storage = GoogleCloudStorage(MagicMock(), **kwargs)

    def tearDown(self):
        super(TestGoogleCloudStorage, self).tearDown()
        patch.stopall()

    def test_list(self):
        """ Can construct a package from a GoogleCloudStorage Blob """
        name, version, filename, summary = "mypkg", "1.2", "pkg.tar.gz", "text"

        blob = self.bucket.blob(name + "/" + filename)
        blob.metadata = {"name": name, "version": version, "summary": summary}
        blob.upload_from_string("foobar")

        package = list(self.storage.list(Package))[0]
        self.assertEqual(package.name, name)
        self.assertEqual(package.version, version)
        self.assertEqual(package.filename, filename)
        self.assertEqual(package.summary, summary)

        self.gcs.bucket.assert_called_with("mybucket")
        self.bucket.list_blobs.assert_called_with(prefix=None)
        self.assertEqual(self.bucket.create.call_count, 0)

    def test_get_url(self):
        """ Mock gcs and test package url generation """
        package = make_package()
        response = self.storage.download_response(package)

        parts = urlparse(response.location)
        self.assertEqual(parts.scheme, "https")
        self.assertEqual(parts.hostname, "storage.googleapis.com")
        self.assertEqual(parts.path, "/mybucket/" + self.storage.get_path(package))
        query = parse_qs(parts.query)
        self.assertItemsEqual(query.keys(), ["Expires", "Signature", "GoogleAccessId"])
        self.assertTrue(int(query["Expires"][0]) > time.time())

    def test_delete(self):
        """ delete() should remove package from storage """
        package = make_package()
        self.storage.upload(package, BytesIO())
        self.storage.delete(package)
        keys = [blob.name for blob in self.bucket.list_blobs()]
        self.assertEqual(len(keys), 0)

    def test_upload(self):
        """ Uploading package sets metadata and sends to S3 """
        package = make_package()
        datastr = b"foobar"
        data = BytesIO(datastr)
        self.storage.upload(package, data)

        blob = self.bucket.list_blobs()[0]
        blob.upload_from_file.assert_called_with(data, predefined_acl=None)

        self.assertEqual(blob._content, datastr)
        self.assertEqual(blob.metadata["name"], package.name)
        self.assertEqual(blob.metadata["version"], package.version)
        self.assertEqual(blob.metadata["summary"], package.summary)

        self.assertEqual(self.bucket.create.call_count, 0)

    def test_upload_prepend_hash(self):
        """ If prepend_hash = True, attach a hash to the file path """
        self.storage.prepend_hash = True
        package = make_package()
        data = BytesIO()
        self.storage.upload(package, data)

        blob = self.bucket.list_blobs()[0]

        pattern = r"^[0-9a-f]{4}/%s/%s$" % (
            re.escape(package.name),
            re.escape(package.filename),
        )
        match = re.match(pattern, blob.name)
        self.assertIsNotNone(match)

    def test_create_bucket(self):
        """ If GCS bucket doesn't exist, create it """
        settings = {
            "storage.bucket": "new_bucket",
            "storage.region_name": "us-east-1",
            "storage.gcp_service_account_json_filename": "my-filename.json",
        }
        storage = GoogleCloudStorage.configure(settings)

        self.gcs.bucket.assert_called_with("new_bucket")
        bucket = self.gcs.bucket("new_bucket")
        bucket.create.assert_called_once_with()

    def test_object_acl(self):
        """ Can specify an object ACL for GCS objects.  Just test to make
            sure that the configured ACL is forwarded to the API client
        """
        settings = dict(self.settings)
        settings["storage.object_acl"] = "authenticated-read"
        kwargs = GoogleCloudStorage.configure(settings)
        storage = GoogleCloudStorage(MagicMock(), **kwargs)
        package = make_package()
        storage.upload(package, BytesIO())

        blob = self.bucket.list_blobs()[0]
        self.assertEqual(blob._acl, "authenticated-read")

    def test_storage_class(self):
        """ Can specify a storage class for GCS objects """
        settings = dict(self.settings)
        settings["storage.storage_class"] = "COLDLINE"
        kwargs = GoogleCloudStorage.configure(settings)
        storage = GoogleCloudStorage(MagicMock(), **kwargs)
        package = make_package()
        storage.upload(package, BytesIO())

        blob = self.bucket.list_blobs()[0]
        blob.update_storage_class.assert_called_with("COLDLINE")

    def test_client_without_credentials(self):
        """ Can create a client without passing in application credentials """
        kwargs = GoogleCloudStorage.configure(
            {"storage.bucket": "new_bucket", "storage.region_name": "us-east-1"}
        )
        GoogleCloudStorage(MagicMock(), **kwargs)
