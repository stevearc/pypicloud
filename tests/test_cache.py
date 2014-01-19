""" Tests for database cache implementations """
from mock import MagicMock, patch
from pypicloud.cache import ICache, SQLCache, RedisCache
from pypicloud.models import Package, SQLPackage, create_schema
from pypicloud.storage import IStorage
from pyramid.testing import DummyRequest
from redis import StrictRedis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from . import DummyCache


try:
    import unittest2 as unittest  # pylint: disable=F0401
except ImportError:
    import unittest


class TestBaseCache(unittest.TestCase):

    """ Tests for the caching base class """

    def test_equality(self):
        """ Two packages with same name & version should be equal """
        p1 = Package('a', '1', 'wibbly')
        p2 = Package('a', '1', 'wobbly')
        self.assertEquals(hash(p1), hash(p2))
        self.assertEquals(p1, p2)

    def test_get_filename(self):
        """ The pypi path should exclude any S3 prefix """
        p1 = Package('a', '1', 'a84f/asodifja/mypath')
        self.assertEqual(p1.filename, 'mypath')

    def test_get_filename_no_prefix(self):
        """ The pypi path should noop if no S3 prefix """
        p1 = Package('a', '1', 'a84f-mypath')
        self.assertEqual(p1.filename, p1.path)

    @patch.object(ICache, 'storage_impl')
    def test_get_url_saves(self, _):
        """ Calls to get_url() saves to caching db if autocommit=True """
        cache = ICache(MagicMock())
        with patch.object(cache, 'save') as save:
            cache.autocommit = True
            package = Package('mypkg', '1.1', 'mypkg-1.1.tar.gz')
            cache.get_url(package)
            save.assert_called_with(package)

    @patch.object(ICache, 'storage_impl')
    def test_get_url_no_save(self, _):
        """ Calls to get_url() doesn't save if autocommit=False """
        cache = ICache(MagicMock())
        cache.autocommit = False
        with patch.object(cache, 'save') as save:
            package = Package('mypkg', '1.1', 'mypkg-1.1.tar.gz')
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


class TestSQLCache(unittest.TestCase):

    """ Tests for the SQLAlchemy cache """

    @classmethod
    def setUpClass(cls):
        super(TestSQLCache, cls).setUpClass()
        engine = create_engine('sqlite:///:memory:')
        create_schema(engine)
        cls.dbmaker = sessionmaker(bind=engine)

    def setUp(self):
        super(TestSQLCache, self).setUp()
        self.sql = self.dbmaker()
        dbmaker = patch.object(SQLCache, 'dbmaker').start()
        storage_impl = patch.object(SQLCache, 'storage_impl').start()
        self.storage = storage_impl.return_value = MagicMock(spec=IStorage)
        dbmaker.return_value = self.sql
        self.db = SQLCache(DummyRequest())

    def tearDown(self):
        super(TestSQLCache, self).tearDown()
        patch.stopall()
        self.sql.rollback()
        self.sql.query(SQLPackage).delete()
        self.sql.commit()

    def test_upload(self):
        """ upload() saves package and uploads to storage """
        pkg = SQLPackage('mypkg', '1.1', 'mypkg')
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
        pkg = SQLPackage('mypkg', '1.1', 'mypkg')
        self.db.save(pkg)
        count = self.sql.query(SQLPackage).count()
        self.assertEqual(count, 1)
        saved_pkg = self.sql.query(SQLPackage).first()
        self.assertEqual(saved_pkg, pkg)

    def test_delete(self):
        """ delete() removes object from database and deletes from storage """
        pkg = SQLPackage('mypkg', '1.1', 'mypkg')
        self.sql.add(pkg)
        self.sql.commit()
        self.db.delete(pkg)
        count = self.sql.query(SQLPackage).count()
        self.assertEqual(count, 0)
        self.storage.delete.assert_called_with(pkg.path)

    def test_clear(self):
        """ clear() removes object from database """
        pkg = SQLPackage('mypkg', '1.1', '/mypkg')
        self.sql.add(pkg)
        self.sql.commit()
        self.db.delete(pkg)
        count = self.sql.query(SQLPackage).count()
        self.assertEqual(count, 0)

    def test_reload(self):
        """ reload_from_storage() inserts packages into the database """
        keys = [
            SQLPackage('mypkg', '1.1', '/mypath'),
            SQLPackage('mypkg2', '1.3.4', '/my/other/path'),
        ]
        self.storage.list.return_value = keys
        self.db.reload_from_storage()
        all_pkgs = self.sql.query(SQLPackage).all()
        self.assertItemsEqual(all_pkgs, keys)

    def test_fetch(self):
        """ fetch() retrieves a package from the database """
        pkg = SQLPackage('mypkg', '1.1', '/mypkg')
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
            SQLPackage('mypkg', '1.1', '/mypath'),
            SQLPackage('mypkg', '1.3', '/mypath3'),
            SQLPackage('mypkg2', '1.3.4', '/my/other/path'),
        ]
        self.sql.add_all(pkgs)
        saved_pkgs = self.db.all('mypkg')
        self.assertItemsEqual(saved_pkgs, pkgs[:2])

    def test_distinct(self):
        """ distinct() returns all unique package names """
        pkgs = [
            SQLPackage('mypkg', '1.1', '/mypath'),
            SQLPackage('mypkg', '1.3', '/mypath3'),
            SQLPackage('mypkg2', '1.3.4', '/my/other/path'),
        ]
        self.sql.add_all(pkgs)
        saved_pkgs = self.db.distinct()
        self.assertItemsEqual(saved_pkgs, set([p.name for p in pkgs]))


class TestRedisCache(unittest.TestCase):

    """ Tests for the redis cache """

    @classmethod
    def setUpClass(cls):
        super(TestRedisCache, cls).setUpClass()
        cls.redis = StrictRedis()

    def setUp(self):
        super(TestRedisCache, self).setUp()
        storage_impl = patch.object(RedisCache, 'storage_impl').start()
        self.storage = storage_impl.return_value = MagicMock(spec=IStorage)
        self.db = RedisCache(DummyRequest())
        RedisCache.db = self.redis

    def tearDown(self):
        super(TestRedisCache, self).tearDown()
        self.redis.flushdb()
        patch.stopall()

    def assert_in_redis(self, pkg):
        """ Assert that a package exists in redis """
        self.assertTrue(self.redis.sismember(self.db.redis_set, pkg.name))
        data = self.redis.hgetall(self.db.redis_key(pkg))
        pkg_data = {
            'name': pkg.name,
            'version': pkg.version,
            'path': pkg.path,
        }
        if pkg.url is not None:
            pkg_data['url'] = pkg.url
            pkg_data['expire'] = pkg.expire.strftime('%s.%f')

        self.assertEqual(data, pkg_data)

    def test_delete(self):
        """ delete() removes object from database and deletes from storage """
        pkg = Package('mypkg', '1.1', 'mypkg-1.1.tar.gz')
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
        pkg = Package('mypkg', '1.1', 'mypkg-1.1.tar.gz')
        key = self.db.redis_key(pkg)
        self.redis[key] = 'foobar'
        self.db.clear(pkg)
        val = self.redis.get(key)
        self.assertIsNone(val)
        count = self.redis.scard(self.db.redis_set)
        self.assertEqual(count, 0)

    def test_reload(self):
        """ reload_from_storage() inserts packages into the database """
        keys = [
            Package('mypkg', '1.1', '/mypath'),
            Package('mypkg2', '1.3.4', '/my/other/path'),
        ]
        self.storage.list.return_value = keys
        self.db.reload_from_storage()
        for pkg in keys:
            self.assert_in_redis(pkg)

    def test_fetch(self):
        """ fetch() retrieves a package from the database """
        pkg = Package('mypkg', '1.1', '/mypkg')
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
            Package('mypkg', '1.1', '/mypath'),
            Package('mypkg', '1.3', '/mypath3'),
            Package('mypkg2', '1.3.4', '/my/other/path'),
        ]
        for pkg in pkgs:
            self.db.save(pkg)
        saved_pkgs = self.db.all('mypkg')
        self.assertItemsEqual(saved_pkgs, pkgs[:2])

    def test_distinct(self):
        """ distinct() returns all unique package names """
        pkgs = [
            Package('mypkg', '1.1', '/mypath'),
            Package('mypkg', '1.3', '/mypath3'),
            Package('mypkg2', '1.3.4', '/my/other/path'),
        ]
        for pkg in pkgs:
            self.db.save(pkg)
        saved_pkgs = self.db.distinct()
        self.assertItemsEqual(saved_pkgs, set([p.name for p in pkgs]))
