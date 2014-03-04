""" Tests for database cache implementations """
from datetime import datetime

import transaction
from mock import MagicMock, patch
from pyramid.testing import DummyRequest

from . import DummyCache, DummyStorage
from pypicloud.cache import ICache, SQLCache, RedisCache
from pypicloud.cache.sql import SQLPackage
from pypicloud.models import Package
from pypicloud.storage import IStorage


try:
    import unittest2 as unittest  # pylint: disable=F0401
except ImportError:
    import unittest


def make_package(name='mypkg', version='1.1', path='mypkg.tar.gz',
                 last_modified=datetime.utcnow(), factory=Package, **kwargs):
    """ Convenience method for constructing a package """
    return factory(name, version, path, last_modified, **kwargs)


class TestBaseCache(unittest.TestCase):

    """ Tests for the caching base class """

    def test_equality(self):
        """ Two packages with same name & version should be equal """
        p1 = make_package(path='wibbly')
        p2 = make_package(path='wobbly')
        self.assertEquals(hash(p1), hash(p2))
        self.assertEquals(p1, p2)

    def test_get_filename(self):
        """ The pypi path should exclude any S3 prefix """
        p1 = make_package(path='a84f/asodifja/mypath')
        self.assertEqual(p1.filename, 'mypath')

    def test_get_filename_no_prefix(self):
        """ The pypi path should noop if no S3 prefix """
        p1 = make_package(path='a84f-mypath')
        self.assertEqual(p1.filename, p1.path)

    @patch.object(ICache, 'storage_impl')
    def test_get_url_saves(self, _):
        """ Calls to get_url() saves to caching db if changed=True """
        cache = ICache(MagicMock())
        cache.storage.get_url.return_value = 'a', True
        with patch.object(cache, 'save') as save:
            package = make_package()
            cache.get_url(package)
            save.assert_called_with(package)

    @patch.object(ICache, 'storage_impl')
    def test_get_url_no_save(self, _):
        """ Calls to get_url() doesn't save if changed=False """
        cache = ICache(MagicMock())
        cache.storage.get_url.return_value = 'a', False
        with patch.object(cache, 'save') as save:
            package = make_package()
            cache.get_url(package)
            self.assertFalse(save.called)

    def test_upload_overwrite(self):
        """ Uploading a preexisting packages overwrites current package """
        cache = DummyCache()
        cache.allow_overwrite = True
        name, version = 'a', '1'
        old_path = 'old_package_path-1.tar.gz'
        cache.upload(name, version, old_path, None)
        new_path = 'new_path-1.tar.gz'
        cache.upload(name, version, new_path, None)

        all_versions = cache.all(name)
        self.assertEqual(len(all_versions), 1)
        self.assertEquals(all_versions[0].path, new_path)

        stored_pkgs = list(cache.storage.list(cache.package_class))
        self.assertEqual(len(stored_pkgs), 1)

    def test_upload_no_overwrite(self):
        """ If allow_overwrite=False duplicate package throws exception """
        cache = DummyCache()
        cache.allow_overwrite = False
        name, version = 'a', '1'
        old_path = 'old_package_path-1.tar.gz'
        cache.upload(name, version, old_path, None)
        new_path = 'new_path-1.tar.gz'
        with self.assertRaises(ValueError):
            cache.upload(name, version, new_path, None)

    def test_configure_storage(self):
        """ Calling configure() sets up storage backend """
        settings = {
            'pypi.storage': 'tests.DummyStorage'
        }
        ICache.configure(settings)
        self.assertEqual(ICache.storage_impl, DummyStorage)

    def test_summary(self):
        """ summary constructs per-package metadata summary """
        cache = DummyCache()
        cache.upload('pkg1', '0.3', 'pkg1.tar.gz', None)
        cache.upload('pkg1', '1.1', 'pkg1.tar.gz', None)
        p1 = cache.upload('pkg1', '1.1.1a2', 'pkg1a2.tar.gz', None)
        p2 = cache.upload('pkg2', '0.1dev2', 'pkg2.tar.gz', None)
        summaries = cache.summary()
        self.assertItemsEqual(summaries, [
            {
                'name': 'pkg1',
                'stable': '1.1',
                'unstable': '1.1.1a2',
                'last_modified': p1.last_modified,
            },
            {
                'name': 'pkg2',
                'stable': None,
                'unstable': '0.1dev2',
                'last_modified': p2.last_modified,
            },
        ])

    def test_reload_if_needed(self):
        """ Reload the cache if it's empty """
        with patch.object(DummyCache, 'reload_from_storage') as reload_pkgs:
            DummyCache.reload_if_needed()
            self.assertTrue(reload_pkgs.called)

    @patch.object(ICache, 'reload_from_storage')
    @patch.object(ICache, 'distinct')
    def test_no_reload_if_needed(self, distinct, reload_pkgs):
        """ Don't reload the cache if it's not necessary """
        distinct.return_value = ['hi']
        ICache.reload_if_needed()
        self.assertFalse(reload_pkgs.called)

    def test_abstract_methods(self):
        """ Abstract methods raise exception """
        settings = {
            'pypi.storage': 'tests.DummyStorage'
        }
        ICache.configure(settings)
        cache = ICache()
        with self.assertRaises(NotImplementedError):
            cache.distinct()
        with self.assertRaises(NotImplementedError):
            cache.fetch('pkg', '1.1')
        with self.assertRaises(NotImplementedError):
            cache.all('pkg')
        with self.assertRaises(NotImplementedError):
            cache.clear(make_package())
        with self.assertRaises(NotImplementedError):
            cache.clear_all()
        with self.assertRaises(NotImplementedError):
            cache.save(make_package())


class TestSQLCache(unittest.TestCase):

    """ Tests for the SQLAlchemy cache """

    @classmethod
    def setUpClass(cls):
        super(TestSQLCache, cls).setUpClass()
        settings = {
            'pypi.storage': 'tests.DummyStorage',
            'db.url': 'sqlite:///:memory:',
        }
        SQLCache.configure(settings)

    def setUp(self):
        super(TestSQLCache, self).setUp()
        self.request = DummyRequest()
        self.db = SQLCache(self.request)
        self.sql = self.db.db
        self.storage = self.db.storage = MagicMock(spec=IStorage)

    def tearDown(self):
        super(TestSQLCache, self).tearDown()
        transaction.abort()
        self.sql.query(SQLPackage).delete()
        transaction.commit()
        self.request._process_finished_callbacks()

    def test_upload(self):
        """ upload() saves package and uploads to storage """
        pkg = make_package(factory=SQLPackage)
        self.storage.upload.return_value = pkg.path
        self.db.upload(pkg.name, pkg.version, pkg.path, None)
        count = self.sql.query(SQLPackage).count()
        self.assertEqual(count, 1)
        saved_pkg = self.sql.query(SQLPackage).first()
        self.assertEqual(saved_pkg, pkg)
        self.storage.upload.assert_called_with(pkg.name, pkg.version, pkg.path,
                                               None)

    def test_save(self):
        """ save() puts object into database """
        pkg = make_package(factory=SQLPackage)
        self.db.save(pkg)
        count = self.sql.query(SQLPackage).count()
        self.assertEqual(count, 1)
        saved_pkg = self.sql.query(SQLPackage).first()
        self.assertEqual(saved_pkg, pkg)

    def test_delete(self):
        """ delete() removes object from database and deletes from storage """
        pkg = make_package(factory=SQLPackage)
        self.sql.add(pkg)
        transaction.commit()
        self.sql.add(pkg)
        self.db.delete(pkg)
        count = self.sql.query(SQLPackage).count()
        self.assertEqual(count, 0)
        self.storage.delete.assert_called_with(pkg.path)

    def test_clear(self):
        """ clear() removes object from database """
        pkg = make_package(factory=SQLPackage)
        self.sql.add(pkg)
        transaction.commit()
        self.sql.add(pkg)
        self.db.delete(pkg)
        count = self.sql.query(SQLPackage).count()
        self.assertEqual(count, 0)

    def test_reload(self):
        """ reload_from_storage() inserts packages into the database """
        keys = [
            make_package(factory=SQLPackage),
            make_package('mypkg2', '1.3.4', 'my/other/path',
                         factory=SQLPackage),
        ]
        self.storage.list.return_value = keys
        self.db.reload_from_storage()
        all_pkgs = self.sql.query(SQLPackage).all()
        self.assertItemsEqual(all_pkgs, keys)

    def test_fetch(self):
        """ fetch() retrieves a package from the database """
        pkg = make_package(factory=SQLPackage)
        self.sql.add(pkg)
        saved_pkg = self.db.fetch(pkg.name, pkg.version)
        self.assertEqual(saved_pkg, pkg)

    def test_fetch_missing(self):
        """ fetch() returns None if no package exists """
        saved_pkg = self.db.fetch('missing_pkg', '1.2')
        self.assertIsNone(saved_pkg)

    def test_all_versions(self):
        """ all() returns all versions of a package """
        pkgs = [
            make_package(factory=SQLPackage),
            make_package(version='1.3', path='mypath3', factory=SQLPackage),
            make_package('mypkg2', '1.3.4', 'my/other/path',
                         factory=SQLPackage),
        ]
        self.sql.add_all(pkgs)
        saved_pkgs = self.db.all('mypkg')
        self.assertItemsEqual(saved_pkgs, pkgs[:2])

    def test_distinct(self):
        """ distinct() returns all unique package names """
        pkgs = [
            make_package(factory=SQLPackage),
            make_package(version='1.3', path='mypath3', factory=SQLPackage),
            make_package('mypkg2', '1.3.4', 'my/other/path',
                         factory=SQLPackage),
        ]
        self.sql.add_all(pkgs)
        saved_pkgs = self.db.distinct()
        self.assertItemsEqual(saved_pkgs, set([p.name for p in pkgs]))

    def test_summary(self):
        """ summary constructs per-package metadata summary """
        self.storage.upload.side_effect = lambda x, y, z, _: z
        self.db.upload('pkg1', '0.3', 'pkg1.tar.gz', None)
        self.db.upload('pkg1', '1.1', 'pkg1.tar.gz', None)
        p1 = self.db.upload('pkg1', '1.1.1a2', 'pkg1a2.tar.gz', None)
        p2 = self.db.upload('pkg2', '0.1dev2', 'pkg2.tar.gz', None)
        summaries = self.db.summary()
        self.assertItemsEqual(summaries, [
            {
                'name': 'pkg1',
                'stable': '1.1',
                'unstable': '1.1.1a2',
                'last_modified': p1.last_modified,
            },
            {
                'name': 'pkg2',
                'stable': None,
                'unstable': '0.1dev2',
                'last_modified': p2.last_modified,
            },
        ])

    def test_reload_if_needed(self):
        """ Reload the cache if it's empty """
        with patch.object(SQLCache, 'storage_impl') as storage_impl:
            storage_impl().list.return_value = [
                make_package(factory=SQLPackage)
            ]
            SQLCache.reload_if_needed()
            count = self.sql.query(SQLPackage).count()
            self.assertEqual(count, 1)


class TestRedisCache(unittest.TestCase):

    """ Tests for the redis cache """

    @classmethod
    def setUpClass(cls):
        super(TestRedisCache, cls).setUpClass()
        settings = {
            'pypi.storage': 'tests.DummyStorage',
            'db.url': 'redis://localhost',
        }
        RedisCache.configure(settings)
        cls.redis = RedisCache.db

    def setUp(self):
        super(TestRedisCache, self).setUp()
        self.db = RedisCache(DummyRequest())
        self.storage = self.db.storage = MagicMock(spec=IStorage)

    def tearDown(self):
        super(TestRedisCache, self).tearDown()
        self.redis.flushdb()

    def assert_in_redis(self, pkg):
        """ Assert that a package exists in redis """
        self.assertTrue(self.redis.sismember(self.db.redis_set, pkg.name))
        data = self.redis.hgetall(self.db.redis_key(pkg))
        pkg_data = {
            'name': pkg.name,
            'version': pkg.version,
            'path': pkg.path,
            'last_modified': pkg.last_modified.strftime('%s.%f'),
        }
        pkg_data.update(pkg.data)

        self.assertEqual(data, pkg_data)

    def test_load(self):
        """ Loading from redis deserializes all fields """
        kwargs = {
            'url': 'my.url',
            'expire': 7237,
        }
        pkg = make_package(**kwargs)
        self.db.save(pkg)

        loaded = self.db.fetch(pkg.name, pkg.version)
        self.assertEqual(loaded.name, pkg.name)
        self.assertEqual(loaded.version, pkg.version)
        self.assertEqual(loaded.path, pkg.path)
        self.assertEqual(loaded.last_modified, pkg.last_modified)
        self.assertEqual(loaded.data, kwargs)

    def test_delete(self):
        """ delete() removes object from database and deletes from storage """
        pkg = make_package()
        key = self.db.redis_key(pkg)
        self.redis[key] = 'foobar'
        self.db.delete(pkg)
        val = self.redis.get(key)
        self.assertIsNone(val)
        count = self.redis.scard(self.db.redis_set)
        self.assertEqual(count, 0)
        self.storage.delete.assert_called_with(pkg.path)

    def test_clear(self):
        """ clear() removes object from database """
        pkg = make_package()
        key = self.db.redis_key(pkg)
        self.redis[key] = 'foobar'
        self.db.clear(pkg)
        val = self.redis.get(key)
        self.assertIsNone(val)
        count = self.redis.scard(self.db.redis_set)
        self.assertEqual(count, 0)

    def test_clear_leave_distinct(self):
        """ clear() doesn't remove package from list of distinct """
        p1 = make_package()
        p2 = make_package(version='1.2')
        self.db.save(p1)
        self.db.save(p2)
        key = self.db.redis_key(p1)
        self.db.clear(p1)
        val = self.redis.get(key)
        self.assertIsNone(val)
        count = self.redis.scard(self.db.redis_set)
        self.assertEqual(count, 1)

    def test_clear_all(self):
        """ clear_all() removes all packages from db """
        p1 = make_package()
        p2 = make_package(version='1.2')
        self.db.save(p1)
        self.db.save(p2)
        key = self.db.redis_key(p1)
        self.db.clear_all()
        val = self.redis.get(key)
        self.assertIsNone(val)
        count = self.redis.scard(self.db.redis_set)
        self.assertEqual(count, 0)

    def test_reload(self):
        """ reload_from_storage() inserts packages into the database """
        keys = [
            make_package(factory=SQLPackage),
            make_package('mypkg2', '1.3.4', 'my/other/path',
                         factory=SQLPackage),
        ]
        self.storage.list.return_value = keys
        self.db.reload_from_storage()
        for pkg in keys:
            self.assert_in_redis(pkg)

    def test_fetch(self):
        """ fetch() retrieves a package from the database """
        pkg = make_package()
        self.db.save(pkg)
        saved_pkg = self.db.fetch(pkg.name, pkg.version)
        self.assertEqual(saved_pkg, pkg)

    def test_fetch_missing(self):
        """ fetch() returns None if no package exists """
        saved_pkg = self.db.fetch('missing_pkg', '1.2')
        self.assertIsNone(saved_pkg)

    def test_all_versions(self):
        """ all() returns all versions of a package """
        pkgs = [
            make_package(factory=SQLPackage),
            make_package(version='1.3', path='mypath3', factory=SQLPackage),
            make_package('mypkg2', '1.3.4', 'my/other/path',
                         factory=SQLPackage),
        ]
        for pkg in pkgs:
            self.db.save(pkg)
        saved_pkgs = self.db.all('mypkg')
        self.assertItemsEqual(saved_pkgs, pkgs[:2])

    def test_distinct(self):
        """ distinct() returns all unique package names """
        pkgs = [
            make_package(factory=SQLPackage),
            make_package(version='1.3', path='mypath3', factory=SQLPackage),
            make_package('mypkg2', '1.3.4', 'my/other/path',
                         factory=SQLPackage),
        ]
        for pkg in pkgs:
            self.db.save(pkg)
        saved_pkgs = self.db.distinct()
        self.assertItemsEqual(saved_pkgs, set([p.name for p in pkgs]))
