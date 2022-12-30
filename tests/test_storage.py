# -*- coding: utf-8 -*-
""" Tests for package storage backends """
import json
import os
import re
import shutil
import tempfile
import time
import unittest
from io import BytesIO
from urllib.parse import parse_qs, urlparse

import boto3
import requests
from azure.core.exceptions import ResourceExistsError
from botocore.exceptions import ClientError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from mock import ANY, MagicMock, patch
from moto import mock_s3

from pypicloud.models import Package
from pypicloud.storage import (
    CloudFrontS3Storage,
    FileStorage,
    GoogleCloudStorage,
    S3Storage,
    get_storage_impl,
)
from pypicloud.util import EnvironSettings

from . import make_package


class TestS3Storage(unittest.TestCase):

    """Tests for storing packages in S3"""

    def setUp(self):
        super(TestS3Storage, self).setUp()
        self.s3_mock = mock_s3()
        self.s3_mock.start()
        self.settings = EnvironSettings(
            {
                "storage.bucket": "mybucket",
                "storage.aws_access_key_id": "abc",
                "storage.aws_secret_access_key": "bcd",
            },
            {},
        )
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
        """Can construct a package from a S3 Key"""
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
        """Test that list works on old keys with no metadata"""
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
        """Mock s3 and test package url generation"""
        package = make_package()
        response = self.storage.download_response(package)

        parts = urlparse(response.location)
        self.assertEqual(parts.scheme, "https")
        self.assertEqual(parts.hostname, "mybucket.s3.amazonaws.com")
        self.assertEqual(parts.path, "/" + self.storage.get_path(package))
        query = parse_qs(parts.query)
        self.assertCountEqual(query.keys(), ["Expires", "Signature", "AWSAccessKeyId"])
        self.assertTrue(int(query["Expires"][0]) > time.time())
        self.assertEqual(
            query["AWSAccessKeyId"][0], self.settings["storage.aws_access_key_id"]
        )

    def test_delete(self):
        """delete() should remove package from storage"""
        package = make_package()
        self.storage.upload(package, BytesIO(b"test1234"))
        self.storage.delete(package)
        keys = list(self.bucket.objects.all())
        self.assertEqual(len(keys), 0)

    def test_upload(self):
        """Uploading package sets metadata and sends to S3"""
        package = make_package(requires_python="3.6")
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
        self.assertDictContainsSubset(
            package.get_metadata(), Package.read_metadata(key.metadata)
        )

    def test_upload_prepend_hash(self):
        """If prepend_hash = True, attach a hash to the file path"""
        self.storage.prepend_hash = True
        package = make_package()
        data = BytesIO(b"test1234")
        self.storage.upload(package, data)
        key = list(self.bucket.objects.all())[0]

        pattern = r"^[0-9a-f]{4}/%s/%s$" % (
            re.escape(package.name),
            re.escape(package.filename),
        )
        match = re.match(pattern, key.key)
        self.assertIsNotNone(match)

    def test_create_bucket_eu(self):
        """If S3 bucket doesn't exist, create it"""
        settings = EnvironSettings(
            {
                "storage.bucket": "new_bucket",
                "storage.region_name": "eu-central-1",
                "signature_version": "s3v4",
            },
            {},
        )
        S3Storage.configure(settings)

        bucket = self.s3.Bucket("new_bucket")
        bucket.load()

    def test_create_bucket_us(self):
        """If S3 bucket doesn't exist, create it"""
        settings = EnvironSettings(
            {"storage.bucket": "new_bucket", "storage.region_name": "us-west-1"}, {}
        )
        S3Storage.configure(settings)

        bucket = self.s3.Bucket("new_bucket")
        bucket.load()

    def test_object_acl(self):
        """Can specify an object ACL for S3 objects"""
        settings = self.settings.clone()
        settings["storage.object_acl"] = "authenticated-read"
        kwargs = S3Storage.configure(settings)
        storage = S3Storage(MagicMock(), **kwargs)
        package = make_package()
        storage.upload(package, BytesIO(b"abc"))
        acl = list(self.bucket.objects.all())[0].Object().Acl()
        self.assertCountEqual(
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
        """Can specify a storage class for S3 objects"""
        settings = self.settings.clone()
        settings["storage.storage_class"] = "STANDARD_IA"
        kwargs = S3Storage.configure(settings)
        storage = S3Storage(MagicMock(), **kwargs)
        package = make_package()
        storage.upload(package, BytesIO(b"abc"))
        storage_class = list(self.bucket.objects.all())[0].Object().storage_class
        self.assertCountEqual(storage_class, "STANDARD_IA")

    def test_check_health_success(self):
        """check_health returns True for good connection"""
        ok, msg = self.storage.check_health()
        self.assertTrue(ok)

    def test_check_health_fail(self):
        """check_health returns False for bad connection"""
        dbmock = self.storage.bucket.meta.client = MagicMock()

        def throw(*_, **__):
            """Throw an exception"""
            raise ClientError({"Error": {}}, "OP")

        dbmock.head_bucket.side_effect = throw
        ok, msg = self.storage.check_health()
        self.assertFalse(ok)

    def test_unicode_summary(self):
        """Unicode characters in summary will be converted to ascii"""
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

    """Tests for storing packages on S3 with CloudFront in front"""

    def setUp(self):
        super(TestCloudFrontS3Storage, self).setUp()
        self.s3_mock = mock_s3()
        self.s3_mock.start()
        self.settings = EnvironSettings(
            {
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
            },
            {},
        )
        s3 = boto3.resource("s3")
        self.bucket = s3.create_bucket(Bucket="mybucket")
        patch.object(CloudFrontS3Storage, "test", True).start()
        kwargs = CloudFrontS3Storage.configure(self.settings)
        self.storage = CloudFrontS3Storage(MagicMock(), **kwargs)

    def test_get_url(self):
        """Mock s3 and test package url generation"""
        package = make_package(version="1.1+g12345")
        response = self.storage.download_response(package)

        parts = urlparse(response.location)
        self.assertEqual(parts.scheme, "https")
        self.assertEqual(parts.netloc, "abcdef.cloudfront.net")
        self.assertEqual(parts.path, "/bcc4/mypkg/mypkg-1.1%2Bg12345.tar.gz")
        query = parse_qs(parts.query)
        self.assertCountEqual(query.keys(), ["Key-Pair-Id", "Expires", "Signature"])
        self.assertTrue(int(query["Expires"][0]) > time.time())
        self.assertEqual(
            query["Key-Pair-Id"][0], self.settings["storage.cloud_front_key_id"]
        )


class TestFileStorage(unittest.TestCase):

    """Tests for storing packages as local files"""

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
        """Uploading package saves file"""
        package = make_package(requires_python="3.6")
        datastr = b"foobar"
        data = BytesIO(datastr)
        self.storage.upload(package, data)
        filename = self.storage.get_path(package)
        self.assertTrue(os.path.exists(filename))
        with open(filename, "r", encoding="utf-8") as ifile:
            self.assertEqual(ifile.read(), "foobar")
        meta_file = self.storage.get_metadata_path(package)
        self.assertTrue(os.path.exists(meta_file))
        with open(meta_file, "r", encoding="utf-8") as mfile:
            self.assertEqual(json.loads(mfile.read()), package.get_metadata())

    def test_list(self):
        """Can iterate over uploaded packages"""
        package = make_package()
        path = self.storage.get_path(package)
        meta_file = self.storage.get_metadata_path(package)
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as ofile:
            ofile.write("foobar")

        with open(meta_file, "w", encoding="utf-8") as mfile:
            mfile.write(json.dumps({"summary": package.summary}))

        pkg = list(self.storage.list(Package))[0]
        self.assertEqual(pkg.name, package.name)
        self.assertEqual(pkg.version, package.version)
        self.assertEqual(pkg.filename, package.filename)
        self.assertEqual(pkg.summary, package.summary)

    def test_delete(self):
        """delete() should remove package from storage"""
        package = make_package()
        path = self.storage.get_path(package)
        meta_path = self.storage.get_metadata_path(package)
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as ofile:
            ofile.write("foobar")
        with open(meta_path, "w", encoding="utf-8") as mfile:
            mfile.write("foobar")
        self.storage.delete(package)
        self.assertFalse(os.path.exists(path))
        self.assertFalse(os.path.exists(meta_path))

    def test_create_package_dir(self):
        """configure() will create the package dir if it doesn't exist"""
        tempdir = tempfile.mkdtemp()
        os.rmdir(tempdir)
        settings = {"storage.dir": tempdir}
        FileStorage.configure(settings)
        try:
            self.assertTrue(os.path.exists(tempdir))
        finally:
            os.rmdir(tempdir)

    def test_check_health(self):
        """Base check_health returns True"""
        ok, msg = self.storage.check_health()
        self.assertTrue(ok)


class TestGoogleCloudStorage(unittest.TestCase):

    """Tests for storing packages in GoogleCloud"""

    def setUp(self):
        super(TestGoogleCloudStorage, self).setUp()
        self._config_file = tempfile.mktemp()
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")
        # to generate a signed url, the client tries to talk to the oauth2 endpoint (token_uri below), which is not implemented in fake-gcs-server ref https://github.com/fsouza/fake-gcs-server/issues/952#issuecomment-1366690110
        # patch this request, so we can still use the service account setup for tests as before, instead of switching to AnonymousCredentials
        patch(
            # https://github.com/googleapis/google-auth-library-python/blob/v2.15.0/google/oauth2/service_account.py#L429
            "google.oauth2.service_account._client",
            # https://github.com/googleapis/google-auth-library-python/blob/v2.15.0/google/oauth2/_client.py#L264
            **{"jwt_grant.return_value": ("mock42", None, {})}
        ).start()
        with open(self._config_file, "w", encoding="utf-8") as ofile:
            json.dump(
                {
                    "client_email": "a@bc.de",
                    "token_uri": "http://localhost:4443/oauth2/v3/certs",
                    "private_key": pem,
                },
                ofile,
            )
        self.settings = {
            "pypi.storage": "gcs",
            "storage.bucket": "mybucket",
            "storage.gcp_project_id": "test",
            "storage.gcp_api_endpoint": "http://localhost:4443",
            "storage.gcp_service_account_json_filename": self._config_file,
        }
        try:
            requests.get(self.settings["storage.gcp_api_endpoint"])
        except requests.ConnectionError as exc:
            raise unittest.SkipTest("Couldn't connect to fake-gcs-server") from exc
        kwargs = GoogleCloudStorage.configure(self.settings)
        self.storage = GoogleCloudStorage(MagicMock(), **kwargs)
        self.bucket = self.storage.bucket

    def tearDown(self):
        super(TestGoogleCloudStorage, self).tearDown()
        patch.stopall()
        os.remove(self._config_file)

    def test_list(self):
        """Can construct a package from a GoogleCloudStorage Blob"""
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
        """Mock gcs and test package url generation"""
        package = make_package()
        response = self.storage.download_response(package)

        parts = urlparse(response.location)
        self.assertEqual(parts.path, "/mybucket/" + self.storage.get_path(package))

    def test_delete(self):
        """delete() should remove package from storage"""
        package = make_package()
        datastr = b"test1234"
        self.storage.upload(package, BytesIO(datastr))
        self.assertEqual(self.storage.open(package).read(), datastr)

        self.storage.delete(package)
        keys = [blob.name for blob in self.bucket.list_blobs()]
        self.assertEqual(len(keys), 0)

    def test_upload(self):
        """Uploading package sets metadata and sends to gcs"""
        package = make_package(requires_python="3.6")
        datastr = b"foobar"
        data = BytesIO(datastr)
        self.storage.upload(package, data)

        self.assertEqual(self.storage.open(package).read(), datastr)

        blob = self.bucket.list_blobs()[0]

        self.assertEqual(blob._content, datastr)
        self.assertEqual(blob.metadata["name"], package.name)
        self.assertEqual(blob.metadata["version"], package.version)
        self.assertDictContainsSubset(package.get_metadata(), blob.metadata)

        self.assertEqual(self.bucket.create.call_count, 0)

    def test_upload_prepend_hash(self):
        """If prepend_hash = True, attach a hash to the file path"""
        self.storage.prepend_hash = True
        package = make_package()
        data = BytesIO(b"test1234")
        self.storage.upload(package, data)

        blob = self.bucket.list_blobs()[0]

        pattern = r"^[0-9a-f]{4}/%s/%s$" % (
            re.escape(package.name),
            re.escape(package.filename),
        )
        match = re.match(pattern, blob.name)
        self.assertIsNotNone(match)

    def test_object_acl(self):
        """Can specify an object ACL for GCS objects.  Just test to make
        sure that the configured ACL is forwarded to the API client
        """
        settings = self.settings.copy()
        settings["storage.object_acl"] = "authenticated-read"
        kwargs = GoogleCloudStorage.configure(self.settings)
        storage = GoogleCloudStorage(MagicMock(), **kwargs)
        package = make_package()
        storage.upload(package, BytesIO(b"test1234"))

        blob = self.bucket.list_blobs()[0]
        self.assertEqual(blob.acl, "authenticated-read")

    def test_storage_class(self):
        """Can specify a storage class for GCS objects"""
        settings = self.settings.copy()
        settings["storage.storage_class"] = "COLDLINE"
        kwargs = GoogleCloudStorage.configure(self.settings)
        storage = GoogleCloudStorage(MagicMock(), **kwargs)
        package = make_package()
        storage.upload(package, BytesIO(b"test1234"))

        blob = self.bucket.list_blobs()[0]
        self.assertEqual(blob.storage_class, "COLDLINE")

    def test_client_without_credentials(self):
        """Can create a client without passing in application credentials"""
        kwargs = GoogleCloudStorage.configure(
            {"storage.bucket": "new_bucket", "storage.region_name": "us-east-1"}
        )
        GoogleCloudStorage(MagicMock(), **kwargs)


class TestAzureStorage(unittest.TestCase):
    """Tests for storing packages in Azure Blob Storage"""

    def setUp(self):
        super(TestAzureStorage, self).setUp()
        self.settings = {
            "pypi.storage": "azure-blob",
            "storage.storage_account_name": "devstoreaccount1",
            "storage.storage_account_key": "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==",  # https://github.com/Azure/Azurite#default-storage-account
            "storage.storage_account_url": "http://devstoreaccount1.azurite:10000",
            "storage.storage_container_name": "pypi",
        }
        try:
            requests.get(self.settings["storage.storage_account_url"])
        except requests.ConnectionError as exc:
            raise unittest.SkipTest("Couldn't connect to azurite") from exc
        storage_func = get_storage_impl(self.settings)
        self.storage = storage_func(MagicMock())
        try:
            self.storage.container_client.create_container()
        except ResourceExistsError:
            # https://github.com/Azure/Azure-Functions/issues/2166#issuecomment-1159361162
            pass

    def test_illegal_init_options(self):
        """Check that ValueError is thrown for illegal combinations of Azure settings"""
        settings = {"pypi.storage": "azure-blob"}
        # missing account name
        cases = {
            "missing account name": {},
            "missing account key": {"storage.storage_account_name": "devstoreaccount1"},
            "missing container name": {
                "storage.storage_account_name": "devstoreaccount1",
                "storage.storage_account_key": "key",
            },
        }
        for setting in cases.values():
            with self.assertRaisesRegex(ValueError, "You must specify"):
                get_storage_impl({**settings, **setting})(MagicMock())

    def test_list_and_upload(self):
        """List packages from blob storage"""
        package = make_package("mypkg", "1.2", "pkg.tar.gz", summary="test")
        datastr = b"test1234"
        self.storage.upload(package, BytesIO(datastr))

        self.assertEqual(self.storage.open(package).read(), datastr)

        package = list(self.storage.list(Package))[0]
        self.assertEqual(package.name, "mypkg")
        self.assertEqual(package.version, "1.2")
        self.assertEqual(package.filename, "pkg.tar.gz")
        self.assertEqual(package.summary, "test")

    def test_get_url(self):
        """Test presigned url generation"""
        package = make_package()
        response = self.storage.download_response(package)

        parts = urlparse(response.location)
        self.assertEqual(parts.scheme, "http")
        self.assertEqual(parts.hostname, "devstoreaccount1.azurite")
        self.assertEqual(
            parts.path,
            "/"
            + self.settings["storage.storage_container_name"]
            + "/"
            + self.storage.get_path(package),
        )
        query = parse_qs(parts.query)
        self.assertCountEqual(query.keys(), ["se", "sp", "spr", "sv", "sr", "sig"])

    def test_delete(self):
        """delete() should remove package from storage"""
        package = make_package()
        self.storage.upload(package, BytesIO(b"test1234"))
        self.storage.delete(package)
        packages = list(self.storage.list(Package))
        self.assertEqual(len(packages), 0)

    def test_check_health_success(self):
        """check_health returns True for good connection"""
        ok, msg = self.storage.check_health()
        self.assertTrue(ok)
