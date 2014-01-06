""" Unit tests for model objects """
from boto.s3.key import Key
from mock import patch, MagicMock
from pypicloud.models import Package
from unittest import TestCase

from . import DBTest, RedisTest
from pypicloud import models


# pylint: disable=W0212


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
        request.dbtype = 'sql'
        url = 'http://pypicloud.com/package-1.1.tar.gz'
        key().generate_url.return_value = url
        package = Package('a', 'b', 'c')
        got_url = package.get_url(request)
        self.assertEquals(got_url, url)

        # Now it should be cached
        key().generate_url.return_value = 'bad'
        got_url = package.get_url(request)
        self.assertEquals(got_url, url)

    def test_get_filename(self):
        """ The pypi path should exclude any S3 prefix """
        p1 = Package('a', '1', 'a84f/asodifja/mypath')
        request = MagicMock()
        request.registry.prefix = ''
        self.assertEqual(p1.filename(request), 'mypath')

    def test_get_filename_no_prefix(self):
        """ The pypi path should noop if no S3 prefix """
        p1 = Package('a', '1', 'a84f-mypath')
        request = MagicMock()
        request.registry.prefix = ''
        self.assertEqual(p1.filename(request), p1.path)


class TestSqlOps(DBTest):

    """ Tests for sql operations on the model """

    def test_save(self):
        """ save() puts object into database """
        pkg = Package('mypkg', '1.1', '/mypkg')
        pkg.save(self.request)
        count = self.db.query(Package).count()
        self.assertEqual(count, 1)
        saved_pkg = self.db.query(Package).first()
        self.assertEqual(saved_pkg, pkg)

    def test_delete(self):
        """ delete() removes object from database """
        pkg = Package('mypkg', '1.1', '/mypkg')
        self.db.add(pkg)
        self.db.commit()
        pkg.delete(self.request)
        count = self.db.query(Package).count()
        self.assertEqual(count, 0)

    def test_load(self):
        """ load() inserts packages into the database """
        with patch.object(Package, 'from_key', lambda x: x):
            keys = [
                Package('mypkg', '1.1', '/mypath'),
                Package('mypkg2', '1.3.4', '/my/other/path'),
            ]
            Package._load(self.request, keys)
        all_pkgs = self.db.query(Package).all()
        self.assertItemsEqual(all_pkgs, keys)

    def test_fetch(self):
        """ fetch() retrieves a package from the database """
        pkg = Package('mypkg', '1.1', '/mypkg')
        self.db.add(pkg)
        saved_pkg = Package.fetch(self.request, pkg.name, pkg.version)
        self.assertEqual(saved_pkg, pkg)

    def test_fetch_missing(self):
        """ fetch() returns None if no package exists """
        saved_pkg = Package.fetch(self.request, 'missing_pkg', '1.2')
        self.assertIsNone(saved_pkg)

    def test_all(self):
        """ all() returns all packages """
        pkgs = [
            Package('mypkg', '1.1', '/mypath'),
            Package('mypkg', '1.3', '/mypath3'),
            Package('mypkg2', '1.3.4', '/my/other/path'),
        ]
        self.db.add_all(pkgs)
        saved_pkgs = Package.all(self.request)
        self.assertItemsEqual(saved_pkgs, pkgs)

    def test_all_versions(self):
        """ all() returns all versions of a package """
        pkgs = [
            Package('mypkg', '1.1', '/mypath'),
            Package('mypkg', '1.3', '/mypath3'),
            Package('mypkg2', '1.3.4', '/my/other/path'),
        ]
        self.db.add_all(pkgs)
        saved_pkgs = Package.all(self.request, 'mypkg')
        self.assertItemsEqual(saved_pkgs, pkgs[:2])

    def test_distinct(self):
        """ distinct() returns all unique package names """
        pkgs = [
            Package('mypkg', '1.1', '/mypath'),
            Package('mypkg', '1.3', '/mypath3'),
            Package('mypkg2', '1.3.4', '/my/other/path'),
        ]
        self.db.add_all(pkgs)
        saved_pkgs = Package.distinct(self.request)
        self.assertItemsEqual(saved_pkgs, set([p.name for p in pkgs]))


class TestRedisOps(RedisTest):

    """ Tests for redis operations on the model """

    def setUp(self):
        super(TestRedisOps, self).setUp()
        self.request.registry.expire_after = 86400
        self.request.registry.buffer_time = 3600

    def assert_in_redis(self, pkg):
        """ Assert that a package exists in redis """
        self.assertTrue(self.db.sismember(Package.redis_set(), pkg.name))
        data = self.request.db.hgetall(pkg.redis_key)
        pkg_data = {
            'name': pkg.name,
            'version': pkg.version,
            'path': pkg.path,
        }
        if pkg._url is not None:
            pkg_data['_url'] = pkg._url
            pkg_data['_expire'] = pkg._expire.strftime('%s.%f')

        self.assertEqual(data, pkg_data)

    def test_save_url(self):
        """ calling get_url() will save generated url to redis """
        pkg = Package('mypkg', '1.1', '/mypkg')
        with patch.object(models, 'Key') as key:
            key().generate_url.return_value = 'pkg_url'
            pkg.save(self.request)
            pkg.get_url(self.request)
            self.assertIsNotNone(pkg._url)
            self.assert_in_redis(pkg)

    def test_delete(self):
        """ delete() removes object from database """
        pkg = Package('mypkg', '1.1', '/mypkg')
        self.db[pkg.redis_key] = 'foobar'
        pkg.delete(self.request)
        val = self.db.get(pkg.redis_key)
        self.assertIsNone(val)
        count = self.db.scard(pkg.redis_set())
        self.assertEqual(count, 0)

    def test_load(self):
        """ load() inserts packages into the database """
        with patch.object(Package, 'from_key', lambda x: x):
            keys = [
                Package('mypkg', '1.1', '/mypath'),
                Package('mypkg2', '1.3.4', '/my/other/path'),
            ]
            Package._load(self.request, keys)
        for pkg in keys:
            self.assert_in_redis(pkg)

    def test_fetch(self):
        """ fetch() retrieves a package from the database """
        pkg = Package('mypkg', '1.1', '/mypkg')
        pkg.save(self.request)
        saved_pkg = Package.fetch(self.request, pkg.name, pkg.version)
        self.assertEqual(saved_pkg, pkg)

    def test_fetch_missing(self):
        """ fetch() returns None if no package exists """
        saved_pkg = Package.fetch(self.request, 'missing_pkg', '1.2')
        self.assertIsNone(saved_pkg)

    def test_all(self):
        """ all() returns all packages """
        pkgs = [
            Package('mypkg', '1.1', '/mypath'),
            Package('mypkg', '1.3', '/mypath3'),
            Package('mypkg2', '1.3.4', '/my/other/path'),
        ]
        for pkg in pkgs:
            pkg.save(self.request)
        saved_pkgs = Package.all(self.request)
        self.assertItemsEqual(saved_pkgs, pkgs)

    def test_all_versions(self):
        """ all() returns all versions of a package """
        pkgs = [
            Package('mypkg', '1.1', '/mypath'),
            Package('mypkg', '1.3', '/mypath3'),
            Package('mypkg2', '1.3.4', '/my/other/path'),
        ]
        for pkg in pkgs:
            pkg.save(self.request)
        saved_pkgs = Package.all(self.request, 'mypkg')
        self.assertItemsEqual(saved_pkgs, pkgs[:2])

    def test_distinct(self):
        """ distinct() returns all unique package names """
        pkgs = [
            Package('mypkg', '1.1', '/mypath'),
            Package('mypkg', '1.3', '/mypath3'),
            Package('mypkg2', '1.3.4', '/my/other/path'),
        ]
        for pkg in pkgs:
            pkg.save(self.request)
        saved_pkgs = Package.distinct(self.request)
        self.assertItemsEqual(saved_pkgs, set([p.name for p in pkgs]))
