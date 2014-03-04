""" Tests for package storage backends """
import time
from cStringIO import StringIO
from datetime import datetime

import shutil
import tempfile
from mock import MagicMock, patch
from moto import mock_s3
from urlparse import urlparse, parse_qs

import boto
import os
import pypicloud
import re
from boto.s3.key import Key
from pypicloud.models import Package
from pypicloud.storage import S3Storage, FileStorage


try:
    import unittest2 as unittest  # pylint: disable=F0401
except ImportError:
    import unittest


def make_package(name='a', version='b', path='path/to/file.tar.gz',
                 last_modified=datetime.utcnow(), **kwargs):
    """ Convenience method for constructing a package """
    return Package(name, version, path, last_modified, **kwargs)


class TestS3Storage(unittest.TestCase):

    """ Tests for storing packages in S3 """

    def setUp(self):
        super(TestS3Storage, self).setUp()
        self.s3_mock = mock_s3()
        self.s3_mock.start()
        self.settings = {
            'aws.bucket': 'mybucket',
            'aws.access_key': 'abc',
            'aws.secret_key': 'bcd',
        }
        conn = boto.connect_s3()
        self.bucket = conn.create_bucket('mybucket')
        patch.object(S3Storage, 'test', True).start()
        S3Storage.configure(self.settings)
        self.storage = S3Storage(MagicMock())

    def tearDown(self):
        super(TestS3Storage, self).tearDown()
        patch.stopall()
        self.s3_mock.stop()

    def test_parse(self):
        """ Make sure the deprecated parse method works """
        full_package = 'MyPkg-1.0.1.tgz'
        package, version = self.storage.parse_package_and_version(full_package)
        self.assertEquals(package, 'mypkg')
        self.assertEquals(version, '1.0.1')

    def test_parse_tarball(self):
        """ Make sure the deprecated parse method works """
        full_package = 'MyPkg-1.0.1.tar.gz'
        package, version = self.storage.parse_package_and_version(full_package)
        self.assertEquals(package, 'mypkg')
        self.assertEquals(version, '1.0.1')

    def test_list(self):
        """ Can construct a package from a S3 Key """
        key = Key(self.bucket)
        name, version, path = 'mypkg', '1.2', 'path/to/file.tar.gz'
        key.key = path
        key.set_metadata('name', name)
        key.set_metadata('version', version)
        key.set_contents_from_string('foobar')
        package = list(self.storage.list(Package))[0]
        self.assertEquals(package.name, name)
        self.assertEquals(package.version, version)
        self.assertEquals(package.path, path)

    def test_list_no_metadata(self):
        """ Test that list works on old keys with no metadata """
        key = Key(self.bucket)
        name, version = 'mypkg', '1.2'
        path = 'path/to/%s-%s.tar.gz' % (name, version)
        key.key = path
        key.set_contents_from_string('foobar')
        package = list(self.storage.list(Package))[0]
        self.assertEquals(package.name, name)
        self.assertEquals(package.version, version)
        self.assertEquals(package.path, path)

    def test_get_url(self):
        """ Mock s3 and test package url generation """
        package = make_package()
        url, _ = self.storage.get_url(package)
        self.assertEqual(package.data['url'], url)
        self.assertIsNotNone(package.data.get('expire'))

        parts = urlparse(url)
        self.assertEqual(parts.scheme, 'https')
        self.assertEqual(parts.netloc, 'mybucket.s3.amazonaws.com')
        self.assertEqual(parts.path, '/' + package.path)
        query = parse_qs(parts.query)
        self.assertItemsEqual(query.keys(), ['Expires', 'Signature',
                                             'AWSAccessKeyId'])
        actual_expire = (package.data['expire'] +
                         self.storage.buffer_time)
        self.assertEqual(int(query['Expires'][0]), int(actual_expire))
        self.assertEqual(query['AWSAccessKeyId'][0],
                         self.settings['aws.access_key'])

    def test_get_url_cached(self):
        """ If url is cached and valid, get_url() returns cached url """
        package = make_package(url='abc', expire=time.time() + 10)
        url, _ = self.storage.get_url(package)
        self.assertEqual(package.data['url'], url)
        self.assertEqual(url, 'abc')

    def test_get_url_expire(self):
        """ If url is cached and invalid, get_url() regenerates the url """
        package = make_package(url='abc', expire=time.time() - 10)
        url, _ = self.storage.get_url(package)
        self.assertEqual(package.data['url'], url)
        self.assertIsNotNone(package.data['expire'])

        parts = urlparse(url)
        self.assertEqual(parts.scheme, 'https')
        self.assertEqual(parts.netloc, 'mybucket.s3.amazonaws.com')
        self.assertEqual(parts.path, '/' + package.path)

    def test_delete(self):
        """ delete() should remove package from storage """
        key = Key(self.bucket)
        name, version, path = 'mypkg', '1.2', 'path/to/file.tar.gz'
        key.key = path
        key.set_metadata('name', name)
        key.set_metadata('version', version)
        key.set_contents_from_string('foobar')
        self.storage.delete(key.key)
        new_key = self.bucket.get_key(key.key)
        self.assertIsNone(new_key)

    def test_upload(self):
        """ Uploading package sets metadata and sends to S3 """
        name, version, path = 'a', '1', 'my/path.tar.gz'
        datastr = 'foobar'
        data = StringIO(datastr)
        path = self.storage.upload(name, version, path, data)
        key = self.bucket.get_key(path)
        self.assertEqual(key.get_contents_as_string(), datastr)
        self.assertEqual(key.get_metadata('name'), name)
        self.assertEqual(key.get_metadata('version'), version)

    def test_upload_prepend_hash(self):
        """ If prepend_hash = True, attach a hash to the file path """
        self.storage.prepend_hash = True
        name, version, path = 'a', '1', 'my/path.tar.gz'
        data = StringIO()
        ret = self.storage.upload(name, version, path, data)

        match = re.match(r'^[0-9a-f]{4}/.+$', ret)
        self.assertIsNotNone(match)

    @patch.object(pypicloud.storage.s3, 'boto')
    def test_create_bucket(self, boto_mock):
        """ If S3 bucket doesn't exist, create it """
        conn = boto_mock.connect_s3()
        conn.lookup.return_value = None
        settings = {
            'aws.bucket': 'new_bucket',
            'aws.region': 'us-east-1',
        }
        S3Storage.configure(settings)
        conn.create_bucket.assert_called_with('new_bucket',
                                              location='us-east-1')


class TestFileStorage(unittest.TestCase):

    """ Tests for storing packages as local files """

    def setUp(self):
        super(TestFileStorage, self).setUp()
        self.tempdir = tempfile.mkdtemp()
        settings = {
            'storage.dir': self.tempdir,
        }
        FileStorage.configure(settings)
        self.request = MagicMock()
        self.storage = FileStorage(self.request)

    def tearDown(self):
        super(TestFileStorage, self).tearDown()
        shutil.rmtree(self.tempdir)

    def test_upload(self):
        """ Uploading package saves file """
        name, version, path = 'a', '1', 'my/path.tar.gz'
        datastr = 'foobar'
        data = StringIO(datastr)
        path = self.storage.upload(name, version, path, data)
        filename = os.path.join(self.tempdir, 'a', '1', 'path.tar.gz')
        self.assertTrue(os.path.exists(filename))
        with open(filename, 'r') as ifile:
            self.assertEqual(ifile.read(), 'foobar')

    def test_list(self):
        """ Can iterate over uploaded packages """
        name, version, shortpath = 'a', '1', 'path.tar.gz'
        path = os.path.join(name, version, shortpath)
        filename = os.path.join(self.tempdir, path)
        os.makedirs(os.path.dirname(filename))
        with open(filename, 'w') as ofile:
            ofile.write('foobar')

        package = list(self.storage.list(Package))[0]
        self.assertEquals(package.name, name)
        self.assertEquals(package.version, version)
        self.assertEquals(package.path, path)

    def test_get_url(self):
        """ Test package url generation """
        package = make_package()
        self.request.app_url.side_effect = lambda *x: '/'.join(x)
        url, _ = self.storage.get_url(package)
        expected = 'api/package/%s/%s/download/%s' % (package.name,
                                                      package.version,
                                                      package.filename)
        self.assertEqual(url, expected)

    def test_delete(self):
        """ delete() should remove package from storage """
        name, version, shortpath = 'a', '1', 'path.tar.gz'
        path = os.path.join(name, version, shortpath)
        filename = os.path.join(self.tempdir, path)
        os.makedirs(os.path.dirname(filename))
        with open(filename, 'w') as ofile:
            ofile.write('foobar')
        self.storage.delete(path)
        self.assertFalse(os.path.exists(filename))

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
