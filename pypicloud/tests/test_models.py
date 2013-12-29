""" Unit tests for model objects """
from boto.s3.key import Key
from mock import patch, MagicMock
from pypicloud.models import Package
from unittest import TestCase

from pypicloud import models


class TestPackage(TestCase):

    """ Unit tests for Package model """

    def tearDown(self):
        super(TestPackage, self).tearDown()
        patch.stopall()

    def test_parse(self):
        """ Make sure the deprecated parse method works """
        full_package = 'MyPkg-1.0.1.tgz'
        package, version = Package._parse_package_and_version(full_package)
        self.assertEquals(package, 'mypkg')
        self.assertEquals(version, '1.0.1')

    def test_parse_tarball(self):
        """ Make sure the deprecated parse method works """
        full_package = 'MyPkg-1.0.1.tar.gz'
        package, version = Package._parse_package_and_version(full_package)
        self.assertEquals(package, 'mypkg')
        self.assertEquals(version, '1.0.1')

    def test_equality(self):
        """ Two packages with same name & version should be equal """
        p1 = Package('a', '1', 'wibbly')
        p2 = Package('a', '1', 'wobbly')
        self.assertEquals(hash(p1), hash(p2))
        self.assertEquals(p1, p2)

    def test_from_key(self):
        """ Can construct a package from a S3 Key """
        key = Key(None)
        name, version, path = 'mypkg', '1.2', '/path/to/file.tar.gz'
        key.set_metadata('name', name)
        key.set_metadata('version', version)
        key.key = path
        package = Package.from_key(key)
        self.assertEquals(package.name, name)
        self.assertEquals(package.version, version)
        self.assertEquals(package.path, path)

    def test_from_key_old(self):
        """ Test that from_key works on old keys with no metadata """
        key = Key(None)
        name, version = 'mypkg', '1.2'
        path = '/path/to/%s-%s.tar.gz' % (name, version)
        key.key = path
        package = Package.from_key(key)
        self.assertEquals(package.name, name)
        self.assertEquals(package.version, version)
        self.assertEquals(package.path, path)

    def test_get_url(self):
        """ Mock s3 and test package url generation """
        key = patch.object(models, 'Key').start()
        request = MagicMock()
        request.registry.expire_after = 1000
        request.registry.buffer_time = 10
        url = 'http://pypicloud.com/package-1.1.tar.gz'
        key().generate_url.return_value = url
        package = Package('a', 'b', 'c')
        got_url = package.get_url(request)
        self.assertEquals(got_url, url)

        # Now it should be cached
        key().generate_url.return_value = 'bad'
        got_url = package.get_url(request)
        self.assertEquals(got_url, url)
