""" Tests for package storage backends """
import json
import time
from six import BytesIO

import shutil
import tempfile
from mock import MagicMock, patch
from moto import mock_s3
from six.moves.urllib.parse import urlparse, parse_qs  # pylint: disable=F0401,E0611

import boto3
import os
import pypicloud
import re
from pypicloud.models import Package
from pypicloud.storage import S3Storage, CloudFrontS3Storage, FileStorage
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
            'storage.bucket': 'mybucket',
            'storage.access_key': 'abc',
            'storage.secret_key': 'bcd',
        }
        self.s3 = boto3.resource('s3')
        self.bucket = self.s3.create_bucket(Bucket='mybucket')
        patch.object(S3Storage, 'test', True).start()
        kwargs = S3Storage.configure(self.settings)
        self.storage = S3Storage(MagicMock(), **kwargs)

    def tearDown(self):
        super(TestS3Storage, self).tearDown()
        patch.stopall()
        self.s3_mock.stop()

    def test_list(self):
        """ Can construct a package from a S3 Key """
        name, version, filename, summary = 'mypkg', '1.2', 'pkg.tar.gz', 'text'
        key = self.bucket.Object(name + '/' + filename)
        key.put(Metadata={
            'name': name,
            'version': version,
            'summary': summary,
        }, Body='foobar')
        package = list(self.storage.list(Package))[0]
        self.assertEquals(package.name, name)
        self.assertEquals(package.version, version)
        self.assertEquals(package.filename, filename)
        self.assertEquals(package.summary, summary)

    def test_list_no_metadata(self):
        """ Test that list works on old keys with no metadata """
        name, version = 'mypkg', '1.2'
        filename = '%s-%s.tar.gz' % (name, version)
        key = self.bucket.Object(name + '/' + filename)
        key.put(Body='foobar')
        package = list(self.storage.list(Package))[0]
        self.assertEquals(package.name, name)
        self.assertEquals(package.version, version)
        self.assertEquals(package.filename, filename)
        self.assertEquals(package.summary, None)

    def test_get_url(self):
        """ Mock s3 and test package url generation """
        package = make_package()
        response = self.storage.download_response(package)

        parts = urlparse(response.location)
        self.assertEqual(parts.scheme, 'https')
        self.assertEqual(parts.hostname, 'mybucket.s3.amazonaws.com')
        self.assertEqual(parts.path, '/' + self.storage.get_path(package))
        query = parse_qs(parts.query)
        self.assertItemsEqual(query.keys(), ['Expires', 'Signature',
                                             'AWSAccessKeyId'])
        self.assertTrue(int(query['Expires'][0]) > time.time())
        self.assertEqual(query['AWSAccessKeyId'][0],
                         self.settings['storage.access_key'])

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
        datastr = b'foobar'
        data = BytesIO(datastr)
        self.storage.upload(package, data)
        key = list(self.bucket.objects.all())[0].Object()
        contents = BytesIO()
        key.download_fileobj(contents)
        self.assertEqual(contents.getvalue(), datastr)
        self.assertEqual(key.metadata['name'], package.name)
        self.assertEqual(key.metadata['version'], package.version)
        self.assertEqual(key.metadata['summary'], package.summary)

    def test_upload_prepend_hash(self):
        """ If prepend_hash = True, attach a hash to the file path """
        self.storage.prepend_hash = True
        package = make_package()
        data = BytesIO()
        self.storage.upload(package, data)
        key = list(self.bucket.objects.all())[0]

        pattern = r'^[0-9a-f]{4}/%s/%s$' % (re.escape(package.name),
                                            re.escape(package.filename))
        match = re.match(pattern, key.key)
        self.assertIsNotNone(match)

    def test_create_bucket(self):
        """ If S3 bucket doesn't exist, create it """
        settings = {
            'storage.bucket': 'new_bucket',
            'storage.region': 'us-east-1',
        }
        S3Storage.configure(settings)
        bucket = self.s3.Bucket('new_bucket')
        bucket.load()


class TestCloudFrontS3Storage(unittest.TestCase):

    """ Tests for storing packages on S3 with CloudFront in front """

    def setUp(self):
        super(TestCloudFrontS3Storage, self).setUp()
        self.s3_mock = mock_s3()
        self.s3_mock.start()
        self.settings = {
            'storage.bucket': 'mybucket',
            'storage.access_key': 'abc',
            'storage.secret_key': 'bcd',
            'storage.cloud_front_domain': 'https://abcdef.cloudfront.net',
            'storage.cloud_front_key_file': '',
            'storage.cloud_front_key_string': '-----BEGIN RSA PRIVATE KEY-----\n'
                                              'MIICXQIBAAKBgQDNBN3WHzIgmOEkBVNdBlTR7iGYyUXDVuFRkJlYp/n1/EZf2YtE\n'
                                              'BpxJAgqdwej8beWV16QXOnKXQpsGAeu7x2pvOGFyRGytmLDeUXayfIF/E46w83V2\n'
                                              'r53NOBrlezagqCAz9uafocyNaXlxZfp4tx82sEmpSmHGwd//+n6zgXNC0QIDAQAB\n'
                                              'AoGAd5EIA1GMPYCLhSNp+82ueARGKcHwYrzviU8ob5D/cVtge5P26YRlbxq2sEyf\n'
                                              'oWBCTgJGW5mlrNuWZ4mFPq1NP2X2IU80k/J67KOuOelAykIVQw6q6GAjtmh40x4N\n'
                                              'EekoFzxVqoFKqWOJ1UNP0jNOyfzxU5dfzvw5GOEXob9usjECQQD3++wWCoq+YRCz\n'
                                              '8qqav2M7leoAnDwmCYKpnugDU0NR61sZADS3kJHnhXAbPFQI4dRfETJOkKE/iDph\n'
                                              'G0Rtdfm1AkEA06VoI49wjEMYs4ah3qwpvhuVyxVa9iozIEoDYiVCOOBZw8rX79G4\n'
                                              '+5yzC9ehy9ugWttSA2jigNXVB6ORN3+mLQJBAM47lZizBbXUdZahvp5ZgoZgY65E\n'
                                              'QIWFrUOxYtS5Hyh2qlk9YZozwhOgVp5f6qdEYGD7pTHPeDqk6aAulBbQYW0CQQC4\n'
                                              'hAw2dGd64UQ3v7h/mTkLNKFzXDrhQgkwrVYlyrXhQDcCK2X2/rB3LDYsrOGyCNfU\n'
                                              'XkEyF87g44vGDSQdbnxBAkA1Y+lB/pqdyHMv5RFabkBvU0yQDfekAKHeQ6rS+21g\n'
                                              'dWedUVc1JNnKtb8W/rMfdjg9YLYqUTvoBvp0DjfwdYc4\n'
                                              '-----END RSA PRIVATE KEY-----',
            'storage.cloud_front_key_id': 'key-id'
        }
        s3 = boto3.resource('s3')
        self.bucket = s3.create_bucket(Bucket='mybucket')
        patch.object(CloudFrontS3Storage, 'test', True).start()
        kwargs = CloudFrontS3Storage.configure(self.settings)
        self.storage = CloudFrontS3Storage(MagicMock(), **kwargs)

    def test_get_url(self):
        """ Mock s3 and test package url generation """
        package = make_package(version="1.1+g12345")
        response = self.storage.download_response(package)

        parts = urlparse(response.location)
        self.assertEqual(parts.scheme, 'https')
        self.assertEqual(parts.netloc, 'abcdef.cloudfront.net')
        self.assertEqual(parts.path, '/bcc4/mypkg/mypkg-1.1%2Bg12345.tar.gz')
        query = parse_qs(parts.query)
        self.assertItemsEqual(query.keys(), ['Key-Pair-Id', 'Expires',
                                             'Signature'])
        self.assertTrue(int(query['Expires'][0]) > time.time())
        self.assertEqual(query['Key-Pair-Id'][0],
                         self.settings['storage.cloud_front_key_id'])


class TestFileStorage(unittest.TestCase):

    """ Tests for storing packages as local files """

    def setUp(self):
        super(TestFileStorage, self).setUp()
        self.tempdir = tempfile.mkdtemp()
        settings = {
            'storage.dir': self.tempdir,
        }
        kwargs = FileStorage.configure(settings)
        self.request = MagicMock()
        self.storage = FileStorage(self.request, **kwargs)

    def tearDown(self):
        super(TestFileStorage, self).tearDown()
        shutil.rmtree(self.tempdir)

    def test_upload(self):
        """ Uploading package saves file """
        package = make_package()
        datastr = b'foobar'
        data = BytesIO(datastr)
        self.storage.upload(package, data)
        filename = self.storage.get_path(package)
        self.assertTrue(os.path.exists(filename))
        with open(filename, 'r') as ifile:
            self.assertEqual(ifile.read(), 'foobar')
        meta_file = self.storage.get_metadata_path(package)
        self.assertTrue(os.path.exists(meta_file))
        with open(meta_file, 'r') as mfile:
            self.assertEqual(json.loads(mfile.read()),
                             {'summary': package.summary})

    def test_list(self):
        """ Can iterate over uploaded packages """
        package = make_package()
        path = self.storage.get_path(package)
        meta_file = self.storage.get_metadata_path(package)
        os.makedirs(os.path.dirname(path))
        with open(path, 'w') as ofile:
            ofile.write('foobar')

        with open(meta_file, 'w') as mfile:
            mfile.write(json.dumps({'summary': package.summary}))

        pkg = list(self.storage.list(Package))[0]
        self.assertEquals(pkg.name, package.name)
        self.assertEquals(pkg.version, package.version)
        self.assertEquals(pkg.filename, package.filename)
        self.assertEquals(pkg.summary, package.summary)

    def test_delete(self):
        """ delete() should remove package from storage """
        package = make_package()
        path = self.storage.get_path(package)
        meta_path = self.storage.get_metadata_path(package)
        os.makedirs(os.path.dirname(path))
        with open(path, 'w') as ofile:
            ofile.write('foobar')
        with open(meta_path, 'w') as mfile:
            mfile.write('foobar')
        self.storage.delete(package)
        self.assertFalse(os.path.exists(path))
        self.assertFalse(os.path.exists(meta_path))

    def test_create_package_dir(self):
        """ configure() will create the package dir if it doesn't exist """
        tempdir = tempfile.mkdtemp()
        os.rmdir(tempdir)
        settings = {
            'storage.dir': tempdir,
        }
        FileStorage.configure(settings)
        try:
            self.assertTrue(os.path.exists(tempdir))
        finally:
            os.rmdir(tempdir)
