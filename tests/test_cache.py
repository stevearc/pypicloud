# -*- coding: utf-8 -*-
""" Tests for database cache implementations """
import sys
import transaction
import calendar
from redis import ConnectionError
from mock import MagicMock, patch
from pyramid.testing import DummyRequest
from sqlalchemy.exc import OperationalError

from . import DummyCache, DummyStorage, make_package
from dynamo3 import Throughput
from flywheel.fields.types import UTC
from pypicloud.cache import ICache, SQLCache, RedisCache
from pypicloud.cache.dynamo import DynamoCache, DynamoPackage, PackageSummary
from pypicloud.cache.sql import SQLPackage
from pypicloud.storage import IStorage


try:
    import unittest2 as unittest  # pylint: disable=F0401
except ImportError:
    import unittest


class TestBaseCache(unittest.TestCase):

    """ Tests for the caching base class """

    def test_equality(self):
        """ Two packages with same name & version should be equal """
        p1 = make_package(filename='wibbly')
        p2 = make_package(filename='wobbly')
        self.assertEquals(hash(p1), hash(p2))
        self.assertEquals(p1, p2)

    def test_upload_overwrite(self):
        """ Uploading a preexisting packages overwrites current package """
        cache = DummyCache()
        cache.allow_overwrite = True
        name, filename = 'a', 'a-1.tar.gz'
        cache.upload(filename, 'old', name)
        cache.upload(filename, 'new', name)

        all_versions = cache.all(name)
        self.assertEqual(len(all_versions), 1)
        data = cache.storage.open(all_versions[0])
        self.assertEqual(data, 'new')

        stored_pkgs = list(cache.storage.list(cache.package_class))
        self.assertEqual(len(stored_pkgs), 1)

    def test_upload_no_overwrite(self):
        """ If allow_overwrite=False duplicate package throws exception """
        cache = DummyCache()
        cache.allow_overwrite = False
        name, version, filename = 'a', '1', 'a-1.tar.gz'
        cache.upload(filename, None, name, version)
        with self.assertRaises(ValueError):
            cache.upload(filename, None, name, version)

    def test_multiple_packages_same_version(self):
        """ Can upload multiple packages that have the same version """
        cache = DummyCache()
        cache.allow_overwrite = False
        name, version = 'a', '1'
        path1 = 'old_package_path-1.tar.gz'
        cache.upload(path1, None, name, version)
        path2 = 'new_path-1.whl'
        cache.upload(path2, None, name, version)

        all_versions = cache.all(name)
        self.assertEqual(len(all_versions), 2)
        stored_pkgs = list(cache.storage.list(cache.package_class))
        self.assertEqual(len(stored_pkgs), 2)

    def test_configure_storage(self):
        """ Calling configure() sets up storage backend """
        settings = {
            'pypi.storage': 'tests.DummyStorage'
        }
        kwargs = ICache.configure(settings)
        self.assertTrue(isinstance(kwargs['storage'](), DummyStorage))

    def test_summary(self):
        """ summary constructs per-package metadata summary """
        cache = DummyCache()
        cache.upload('pkg1-0.3.tar.gz', None)
        cache.upload('pkg1-1.1.tar.gz', None)
        p1 = cache.upload('pkg1a2.tar.gz', None, 'pkg1', '1.1.1a2')
        p2 = cache.upload('pkg2.tar.gz', None, 'pkg2', '0.1dev2')
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
        cache = DummyCache()
        cache.reload_from_storage = MagicMock()
        cache.reload_if_empty()
        self.assertTrue(cache.reload_from_storage.called)

    def test_no_reload_if_needed(self):
        """ Don't reload the cache if it's not necessary """
        cache = DummyCache()
        cache.reload_from_storage = MagicMock()
        cache.distinct = MagicMock()
        cache.distinct.return_value = ['hi']
        cache.reload_if_empty()
        self.assertFalse(cache.reload_from_storage.called)

    def test_abstract_methods(self):
        """ Abstract methods raise exception """
        settings = {
            'pypi.storage': 'tests.DummyStorage'
        }
        kwargs = ICache.configure(settings)
        cache = ICache(**kwargs)
        with self.assertRaises(NotImplementedError):
            cache.distinct()
        with self.assertRaises(NotImplementedError):
            cache.fetch('pkg-1.1.tar.gz')
        with self.assertRaises(NotImplementedError):
            cache.all('pkg')
        with self.assertRaises(NotImplementedError):
            cache.clear(make_package())
        with self.assertRaises(NotImplementedError):
            cache.clear_all()
        with self.assertRaises(NotImplementedError):
            cache.save(make_package())


class TestSQLiteCache(unittest.TestCase):

    """ Tests for the SQLAlchemy cache """

    DB_URL = 'sqlite://'

    @classmethod
    def setUpClass(cls):
        super(TestSQLiteCache, cls).setUpClass()
        settings = {
            'pypi.storage': 'tests.DummyStorage',
            'db.url': cls.DB_URL,
        }
        try:
            cls.kwargs = SQLCache.configure(settings)
        except OperationalError:
            raise unittest.SkipTest("Couldn't connect to database")

    def setUp(self):
        super(TestSQLiteCache, self).setUp()
        self.request = DummyRequest()
        self.db = SQLCache(self.request, **self.kwargs)
        self.sql = self.db.db
        self.storage = self.db.storage = MagicMock(spec=IStorage)

    def tearDown(self):
        super(TestSQLiteCache, self).tearDown()
        transaction.abort()
        self.sql.query(SQLPackage).delete()
        transaction.commit()
        self.request._process_finished_callbacks()

    def test_upload(self):
        """ upload() saves package and uploads to storage """
        pkg = make_package(factory=SQLPackage)
        self.db.upload(pkg.filename, None, pkg.name, pkg.version)
        count = self.sql.query(SQLPackage).count()
        self.assertEqual(count, 1)
        saved_pkg = self.sql.query(SQLPackage).first()
        self.assertEqual(saved_pkg, pkg)
        self.storage.upload.assert_called_with(pkg, None)

    def test_upload_overwrite(self):
        """ Uploading a preexisting packages overwrites current package """
        self.db.allow_overwrite = True
        name, filename = 'a', 'a-1.tar.gz'
        self.db.upload(filename, 'old', name)
        self.db.upload(filename, 'new', name)

        all_versions = self.db.all(name)
        self.assertEqual(len(all_versions), 1)

    def test_save(self):
        """ save() puts object into database """
        pkg = make_package(factory=SQLPackage)
        self.db.save(pkg)
        count = self.sql.query(SQLPackage).count()
        self.assertEqual(count, 1)
        saved_pkg = self.sql.query(SQLPackage).first()
        self.assertEqual(saved_pkg, pkg)

    def test_save_unicode(self):
        """ save() can store packages with unicode in the names """
        pkg = make_package(u'mypackage™', factory=SQLPackage)
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
        self.storage.delete.assert_called_with(pkg)

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
        saved_pkg = self.db.fetch(pkg.filename)
        self.assertEqual(saved_pkg, pkg)

    def test_fetch_missing(self):
        """ fetch() returns None if no package exists """
        saved_pkg = self.db.fetch('missing_pkg-1.2.tar.gz')
        self.assertIsNone(saved_pkg)

    def test_all_versions(self):
        """ all() returns all versions of a package """
        pkgs = [
            make_package(factory=SQLPackage),
            make_package(version='1.3', filename='mypath3',
                         factory=SQLPackage),
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
            make_package(version='1.3', filename='mypath3',
                         factory=SQLPackage),
            make_package('mypkg2', '1.3.4', 'my/other/path',
                         factory=SQLPackage),
        ]
        self.sql.add_all(pkgs)
        saved_pkgs = self.db.distinct()
        self.assertItemsEqual(saved_pkgs, set([p.name for p in pkgs]))

    def test_search_or(self):
        """ search() returns packages that match the query """
        pkgs = [
            make_package(factory=SQLPackage),
            make_package('somepackage', version='1.3', filename='mypath3',
                         summary='this is mypkg', factory=SQLPackage),
            make_package('mypkg2', '1.3.4', 'my/other/path',
                         factory=SQLPackage),
            make_package('package', factory=SQLPackage),
        ]
        self.sql.add_all(pkgs)
        criteria = {'name': ['mypkg'], 'summary': ['mypkg']}
        packages = self.db.search(criteria, 'or')
        self.assertItemsEqual(packages, pkgs[:-1])

    def test_search_and(self):
        """ search() returns packages that match the query """
        pkgs = [
            make_package(factory=SQLPackage),
            make_package('somepackage', version='1.3', filename='mypath3',
                         summary='this is mypkg', factory=SQLPackage),
            make_package('mypkg2', '1.3.4', 'my/other/path',
                         factory=SQLPackage),
            make_package('package', factory=SQLPackage),
        ]
        self.sql.add_all(pkgs)
        criteria = {'name': ['my', 'pkg'], 'summary': ['this', 'mypkg']}
        packages = self.db.search(criteria, 'and')
        self.assertItemsEqual(packages, pkgs[:-1])

    def test_summary(self):
        """ summary constructs per-package metadata summary """
        self.db.upload('pkg1-0.3.tar.gz', None, 'pkg1', '0.3')
        self.db.upload('pkg1-1.1.tar.gz', None, 'pkg1', '1.1')
        p1 = self.db.upload('pkg1a2.tar.gz', None, 'pkg1', '1.1.1a2')
        p2 = self.db.upload('pkg2.tar.gz', None, 'pkg2', '0.1dev2')
        s1, s2 = self.db.summary()  # pylint: disable=E0632
        # Order them correctly. assertItemsEqual isn't playing nice in py2.6
        if s1['name'] == 'pkg2':
            s1, s2 = s2, s1
        self.assertEqual(s1['stable'], u'1.1')
        self.assertEqual(s1['unstable'], u'1.1.1a2')
        self.assertIsNone(s2['stable'])
        self.assertEqual(s2['unstable'], u'0.1dev2')
        # last_modified may be rounded when stored in MySQL,
        # so the best we can do is make sure they're close.
        self.assertTrue(
            calendar.timegm(s1['last_modified'].timetuple()) -
            calendar.timegm(p1.last_modified.timetuple()) <= 1)
        self.assertTrue(
            calendar.timegm(s2['last_modified'].timetuple()) -
            calendar.timegm(p2.last_modified.timetuple()) <= 1)

    def test_multiple_packages_same_version(self):
        """ Can upload multiple packages that have the same version """
        with patch.object(self.db, 'allow_overwrite', False):
            name, version = 'a', '1'
            path1 = 'old_package_path-1.tar.gz'
            self.db.upload(path1, None, name, version)
            path2 = 'new_path-1.whl'
            self.db.upload(path2, None, name, version)

            all_versions = self.db.all(name)
            self.assertEqual(len(all_versions), 2)

    def test_reload_if_needed(self):
        """ Reload the cache if it's empty """
        self.db.storage = MagicMock()
        self.db.storage.list.return_value = [
            make_package(factory=SQLPackage)
        ]
        self.db.reload_if_empty()
        count = self.sql.query(SQLPackage).count()
        self.assertEqual(count, 1)


class TestMySQLCache(TestSQLiteCache):
    """ Test the SQLAlchemy cache on a MySQL DB """

    DB_URL = 'mysql://root@127.0.0.1:3306/test?charset=utf8mb4'


class TestPostgresCache(TestSQLiteCache):
    """ Test the SQLAlchemy cache on a Postgres DB """

    DB_URL = 'postgresql://postgres@127.0.0.1:5432/postgres'


class TestRedisCache(unittest.TestCase):

    """ Tests for the redis cache """

    @classmethod
    def setUpClass(cls):
        super(TestRedisCache, cls).setUpClass()
        settings = {
            'pypi.storage': 'tests.DummyStorage',
            'db.url': 'redis://localhost',
        }
        cls.kwargs = RedisCache.configure(settings)
        cls.redis = cls.kwargs['db']
        try:
            cls.redis.flushdb()
        except ConnectionError:
            msg = "Redis not found on port 6379"
            if sys.version_info < (2, 7):
                raise unittest.SkipTest(msg)
            else:
                setattr(
                    cls,
                    "setUp",
                    lambda cls: unittest.TestCase.skipTest(cls, msg),
                )

    def setUp(self):
        super(TestRedisCache, self).setUp()
        self.db = RedisCache(DummyRequest(), **self.kwargs)
        self.storage = self.db.storage = MagicMock(spec=IStorage)

    def tearDown(self):
        super(TestRedisCache, self).tearDown()
        self.redis.flushdb()

    def assert_in_redis(self, pkg):
        """ Assert that a package exists in redis """
        self.assertTrue(self.redis.sismember(self.db.redis_set, pkg.name))
        data = self.redis.hgetall(self.db.redis_key(pkg.filename))
        dt = pkg.last_modified
        lm = calendar.timegm(dt.utctimetuple()) + dt.microsecond / 1000000.0
        lm_str = ("%.6f" % lm).rstrip('0').rstrip('.')
        pkg_data = {
            'name': pkg.name,
            'version': pkg.version,
            'filename': pkg.filename,
            'last_modified': lm_str,
            'summary': pkg.summary,
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

        loaded = self.db.fetch(pkg.filename)
        self.assertEqual(loaded.name, pkg.name)
        self.assertEqual(loaded.version, pkg.version)
        self.assertEqual(loaded.filename, pkg.filename)
        self.assertEqual(loaded.last_modified, pkg.last_modified)
        self.assertEqual(loaded.summary, pkg.summary)
        self.assertEqual(loaded.data, kwargs)

    def test_delete(self):
        """ delete() removes object from database and deletes from storage """
        pkg = make_package()
        key = self.db.redis_key(pkg.filename)
        self.redis[key] = 'foobar'
        self.db.delete(pkg)
        val = self.redis.get(key)
        self.assertIsNone(val)
        count = self.redis.scard(self.db.redis_set)
        self.assertEqual(count, 0)
        self.storage.delete.assert_called_with(pkg)

    def test_clear(self):
        """ clear() removes object from database """
        pkg = make_package()
        key = self.db.redis_key(pkg.filename)
        self.redis[key] = 'foobar'
        self.db.clear(pkg)
        val = self.redis.get(key)
        self.assertIsNone(val)
        count = self.redis.scard(self.db.redis_set)
        self.assertEqual(count, 0)

    def test_clear_leave_distinct(self):
        """ clear() doesn't remove package from list of distinct """
        p1 = make_package()
        p2 = make_package(filename='another-1.2.tar.gz')
        self.db.save(p1)
        self.db.save(p2)
        key = self.db.redis_key(p1.filename)
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
        saved_pkg = self.db.fetch(pkg.filename)
        self.assertEqual(saved_pkg, pkg)

    def test_fetch_missing(self):
        """ fetch() returns None if no package exists """
        saved_pkg = self.db.fetch('missing_pkg-1.2.tar.gz')
        self.assertIsNone(saved_pkg)

    def test_all_versions(self):
        """ all() returns all versions of a package """
        pkgs = [
            make_package(factory=SQLPackage),
            make_package(version='1.3', filename='mypath3',
                         factory=SQLPackage),
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
            make_package(version='1.3', filename='mypath3',
                         factory=SQLPackage),
            make_package('mypkg2', '1.3.4', 'my/other/path',
                         factory=SQLPackage),
        ]
        for pkg in pkgs:
            self.db.save(pkg)
        saved_pkgs = self.db.distinct()
        self.assertItemsEqual(saved_pkgs, set([p.name for p in pkgs]))

    def test_search_or(self):
        """ search() returns packages that match the query """
        pkgs = [
            make_package(factory=SQLPackage),
            make_package('somepackage', version='1.3', filename='mypath3',
                         summary='this is mypkg', factory=SQLPackage),
            make_package('mypkg2', '1.3.4', 'my/other/path',
                         factory=SQLPackage),
            make_package('package', factory=SQLPackage),
        ]
        for pkg in pkgs:
            self.db.save(pkg)
        criteria = {'name': ['mypkg'], 'summary': ['mypkg']}
        packages = self.db.search(criteria, 'or')
        self.assertItemsEqual(packages, pkgs[:-1])

    def test_search_and(self):
        """ search() returns packages that match the query """
        pkgs = [
            make_package(factory=SQLPackage),
            make_package('somepackage', version='1.3', filename='mypath3',
                         summary='this is mypkg', factory=SQLPackage),
            make_package('mypkg2', '1.3.4', 'my/other/path',
                         factory=SQLPackage),
            make_package('package', factory=SQLPackage),
        ]
        for pkg in pkgs:
            self.db.save(pkg)
        criteria = {'name': ['my', 'pkg'], 'summary': ['this', 'mypkg']}
        packages = self.db.search(criteria, 'and')
        self.assertItemsEqual(packages, pkgs[:-1])

    def test_multiple_packages_same_version(self):
        """ Can upload multiple packages that have the same version """
        with patch.object(self.db, 'allow_overwrite', False):
            name, version = 'a', '1'
            path1 = 'old_package_path-1.tar.gz'
            self.db.upload(path1, None, name, version)
            path2 = 'new_path-1.whl'
            self.db.upload(path2, None, name, version)

            all_versions = self.db.all(name)
            self.assertEqual(len(all_versions), 2)


class TestDynamoCache(unittest.TestCase):

    """ Tests for the DynamoCache """

    dynamo = None

    @classmethod
    def setUpClass(cls):
        super(TestDynamoCache, cls).setUpClass()
        host = cls.dynamo.host[cls.dynamo.host.index('//') + 2:]
        host, port = host.split(':')
        settings = {
            'pypi.storage': 'tests.DummyStorage',
            'db.host': host,
            'db.port': port,
            'db.namespace': 'test.',
            'db.access_key': '',
            'db.secret_key': '',
        }
        cls.kwargs = DynamoCache.configure(settings)
        cls.engine = cls.kwargs['engine']

    @classmethod
    def tearDownClass(cls):
        super(TestDynamoCache, cls).tearDownClass()
        cls.engine.delete_schema()

    def setUp(self):
        super(TestDynamoCache, self).setUp()
        self.db = DynamoCache(DummyRequest(), **self.kwargs)
        self.storage = self.db.storage = MagicMock(spec=IStorage)

    def tearDown(self):
        super(TestDynamoCache, self).tearDown()
        for model in (DynamoPackage, PackageSummary):
            self.engine.scan(model).delete()

    def _save_pkgs(self, *pkgs):
        """ Save a DynamoPackage to the db """
        for pkg in pkgs:
            self.engine.save(pkg)
            summary = (self.engine.get(PackageSummary, name=pkg.name) or
                       PackageSummary(pkg))
            summary.update_with(pkg)
            self.engine.sync(summary)

    def test_upload(self):
        """ upload() saves package and uploads to storage """
        pkg = make_package(factory=DynamoPackage)
        self.db.upload(pkg.filename, None, pkg.name, pkg.version)
        count = self.engine.scan(DynamoPackage).count()
        self.assertEqual(count, 1)
        saved_pkg = self.engine.scan(DynamoPackage).first()
        self.assertEqual(saved_pkg, pkg)
        self.storage.upload.assert_called_with(pkg, None)

    def test_save(self):
        """ save() puts object into database """
        pkg = make_package(factory=DynamoPackage)
        self.db.save(pkg)
        count = self.engine.scan(DynamoPackage).count()
        self.assertEqual(count, 1)
        saved_pkg = self.engine.scan(DynamoPackage).first()
        self.assertEqual(saved_pkg, pkg)

    def test_delete(self):
        """ delete() removes object from database and deletes from storage """
        pkg = make_package(factory=DynamoPackage)
        self._save_pkgs(pkg)
        self.db.delete(pkg)
        count = self.engine.scan(DynamoPackage).count()
        self.assertEqual(count, 0)
        count = self.engine.scan(PackageSummary).count()
        self.assertEqual(count, 0)
        self.storage.delete.assert_called_with(pkg)

    def test_clear(self):
        """ clear() removes object from database """
        pkg = make_package(factory=DynamoPackage)
        self._save_pkgs(pkg)
        self.db.delete(pkg)
        count = self.engine.scan(DynamoPackage).count()
        self.assertEqual(count, 0)
        count = self.engine.scan(PackageSummary).count()
        self.assertEqual(count, 0)

    def test_reload(self):
        """ reload_from_storage() inserts packages into the database """
        keys = [
            make_package(factory=DynamoPackage),
            make_package('mypkg2', '1.3.4', 'my/other/path',
                         factory=DynamoPackage),
        ]
        self.storage.list.return_value = keys
        self.db.reload_from_storage()
        all_pkgs = self.engine.scan(DynamoPackage).all()
        self.assertItemsEqual(all_pkgs, keys)

    def test_fetch(self):
        """ fetch() retrieves a package from the database """
        pkg = make_package(factory=DynamoPackage)
        self._save_pkgs(pkg)
        saved_pkg = self.db.fetch(pkg.filename)
        self.assertEqual(saved_pkg, pkg)

    def test_fetch_missing(self):
        """ fetch() returns None if no package exists """
        saved_pkg = self.db.fetch('missing_pkg-1.2.tar.gz')
        self.assertIsNone(saved_pkg)

    def test_all_versions(self):
        """ all() returns all versions of a package """
        pkgs = [
            make_package(factory=DynamoPackage),
            make_package(version='1.3', filename='mypath3',
                         factory=DynamoPackage),
            make_package('mypkg2', '1.3.4', 'my/other/path',
                         factory=DynamoPackage),
        ]
        self._save_pkgs(*pkgs)
        saved_pkgs = self.db.all('mypkg')
        self.assertItemsEqual(saved_pkgs, pkgs[:2])

    def test_distinct(self):
        """ distinct() returns all unique package names """
        pkgs = [
            make_package(factory=DynamoPackage),
            make_package(version='1.3', filename='mypath3',
                         factory=DynamoPackage),
            make_package('mypkg2', '1.3.4', 'my/other/path',
                         factory=DynamoPackage),
        ]
        self._save_pkgs(*pkgs)
        saved_pkgs = self.db.distinct()
        self.assertItemsEqual(saved_pkgs, set([p.name for p in pkgs]))

    def test_search_or(self):
        """ search() returns packages that match the query """
        pkgs = [
            make_package(factory=DynamoPackage),
            make_package('somepackage', version='1.3', filename='mypath3',
                         summary='this is mypkg', factory=DynamoPackage),
            make_package('mypkg2', '1.3.4', 'my/other/path',
                         factory=DynamoPackage),
            make_package('package', factory=DynamoPackage),
        ]
        self._save_pkgs(*pkgs)
        criteria = {'name': ['mypkg'], 'summary': ['mypkg']}
        packages = self.db.search(criteria, 'or')
        self.assertItemsEqual(packages, pkgs[:-1])

    def test_search_and(self):
        """ search() returns packages that match the query """
        pkgs = [
            make_package(factory=DynamoPackage),
            make_package('somepackage', version='1.3', filename='mypath3',
                         summary='this is mypkg', factory=DynamoPackage),
            make_package('mypkg2', '1.3.4', 'my/other/path',
                         factory=DynamoPackage),
            make_package('package', factory=DynamoPackage),
        ]
        self._save_pkgs(*pkgs)
        criteria = {'name': ['my', 'pkg'], 'summary': ['this', 'mypkg']}
        packages = self.db.search(criteria, 'and')
        self.assertItemsEqual(packages, pkgs[:-1])

    def test_summary(self):
        """ summary constructs per-package metadata summary """
        self.db.upload('pkg1-0.3a2.tar.gz', None, 'pkg1', '0.3a2')
        self.db.upload('pkg1-1.1.tar.gz', None, 'pkg1', '1.1')
        p1 = self.db.upload('pkg1a2.tar.gz', None, 'pkg1', '1.1.1a2')
        p2 = self.db.upload('pkg2.tar.gz', None, 'pkg2', '0.1dev2')
        summaries = self.db.summary()
        self.assertItemsEqual(summaries, [
            {
                'name': 'pkg1',
                'stable': '1.1',
                'unstable': '1.1.1a2',
                'last_modified': p1.last_modified.replace(tzinfo=UTC),
            },
            {
                'name': 'pkg2',
                'stable': None,
                'unstable': '0.1dev2',
                'last_modified': p2.last_modified.replace(tzinfo=UTC),
            },
        ])

    def test_multiple_packages_same_version(self):
        """ Can upload multiple packages that have the same version """
        with patch.object(self.db, 'allow_overwrite', False):
            name, version = 'a', '1'
            path1 = 'old_package_path-1.tar.gz'
            self.db.upload(path1, None, name, version)
            path2 = 'new_path-1.whl'
            self.db.upload(path2, None, name, version)

            all_versions = self.db.all(name)
            self.assertEqual(len(all_versions), 2)

    def test_clear_all_keep_throughput(self):
        """ Calling clear_all will keep same table throughput """
        throughput = {}
        for model in (DynamoPackage, PackageSummary):
            tablename = model.meta_.ddb_tablename(self.engine.namespace)
            desc = self.dynamo.describe_table(tablename)
            self.dynamo.update_table(desc.name, Throughput(7, 7))
            for index in desc.global_indexes:
                self.dynamo.update_table(desc.name,
                                         global_indexes={
                                             index.name: Throughput(7, 7)
                                         })

        self.db.clear_all()

        for model in (DynamoPackage, PackageSummary):
            tablename = model.meta_.ddb_tablename(self.engine.namespace)
            desc = self.dynamo.describe_table(tablename)
            self.assertEqual(desc.throughput.read, 7)
            self.assertEqual(desc.throughput.write, 7)
            for index in desc.global_indexes:
                self.assertEqual(index.throughput.read, 7)
                self.assertEqual(index.throughput.write, 7)

    def test_update_wrong_summary(self):
        """ Updating summary with wrong package doesn't blow up """
        pkg1 = make_package('mypkg', '1.0', factory=DynamoPackage)
        pkg2 = make_package('mypkg2', '1.3', factory=DynamoPackage)
        summary = PackageSummary(pkg1)
        summary.update_with(pkg2)
        self.assertEqual(summary.stable, pkg1.version)

    def test_delete_updates_summary(self):
        """ Deleting a package updates the summary """
        pkg1 = make_package('mypkg', '1.0', factory=DynamoPackage)
        pkg2 = make_package('mypkg', '1.3', factory=DynamoPackage)
        self._save_pkgs(pkg1, pkg2)
        self.db.delete(pkg2)
        summary = self.engine.scan(PackageSummary).first()
        self.assertEqual(summary.stable, pkg1.version)

    def test_delete_regression(self):
        """
        Regression test. Dynamo cache would sometimes remove the wrong package.

        See https://github.com/stevearc/pypicloud/issues/118
        """
        pkg1 = make_package('mypkg', '1.0', 'mypkg-1.0.tar.gz',
                            factory=DynamoPackage)
        pkg2 = make_package('mypkg', '1.0', 'mypkg-1.0.whl',
                            factory=DynamoPackage)
        self._save_pkgs(pkg1, pkg2)
        self.db.delete(pkg2)
        pkg = self.engine.scan(DynamoPackage).first()
        self.assertEqual(pkg.filename, pkg1.filename)
