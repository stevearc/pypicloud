""" Tests for gracefully reloading the caches """
import unittest
from datetime import datetime, timedelta

import redis
import transaction
from mock import MagicMock
from pyramid.testing import DummyRequest
from sqlalchemy.exc import OperationalError

from pypicloud.cache import RedisCache, SQLCache
from pypicloud.cache.dynamo import DynamoCache, DynamoPackage, PackageSummary
from pypicloud.cache.sql import SQLPackage
from pypicloud.storage import IStorage

from . import make_package


class TestDynamoCache(unittest.TestCase):

    """ Tests for the DynamoCache """

    dynamo = None

    @classmethod
    def setUpClass(cls):
        super(TestDynamoCache, cls).setUpClass()
        host = cls.dynamo.host[cls.dynamo.host.index("//") + 2 :]
        host, port = host.split(":")
        settings = {
            "pypi.storage": "tests.DummyStorage",
            "db.region_name": "us-east-1",
            "db.host": host,
            "db.port": port,
            "db.namespace": "test.",
            "db.aws_access_key_id": "",
            "db.aws_secret_access_key": "",
            "db.graceful_reload": True,
        }
        cls.kwargs = DynamoCache.configure(settings)
        cls.engine = cls.kwargs["engine"]

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
            summary = PackageSummary(pkg)
            self.engine.save(summary, overwrite=True)

    def test_add_missing(self):
        """ Add missing packages to cache """
        keys = [make_package(factory=DynamoPackage)]
        self.storage.list.return_value = keys
        self.db.reload_from_storage()
        all_pkgs = self.engine.scan(DynamoPackage).all()
        self.assertItemsEqual(all_pkgs, keys)
        all_summaries = self.engine.scan(PackageSummary).all()
        self.assertEqual(len(all_summaries), 1)

    def test_remove_extra(self):
        """ Remove extra packages from cache """
        keys = [
            make_package(factory=DynamoPackage),
            make_package("mypkg2", "1.3.4", factory=DynamoPackage),
        ]
        self.db.save(keys[0])
        self.db.save(keys[1])
        self.storage.list.return_value = keys[:1]
        self.db.reload_from_storage()
        all_pkgs = self.engine.scan(DynamoPackage).all()
        self.assertItemsEqual(all_pkgs, keys[:1])
        # It should have removed the summary as well
        self.assertEqual(self.engine.scan(PackageSummary).count(), 1)

    def test_remove_extra_leave_concurrent(self):
        """ Removing extra packages will leave packages that were uploaded concurrently """
        pkgs = [
            make_package(factory=DynamoPackage),
            make_package("mypkg2", factory=DynamoPackage),
        ]
        self.db.save(pkgs[0])
        self.db.save(pkgs[1])

        # Return first pkgs[1], then pkgs[1:] because the second time we list
        # we will have "uploaded" pkgs[2]
        return_values = [lambda: pkgs[1:2], lambda: pkgs[1:]]

        def list_storage(factory):
            """ mocked method for listing storage packages """
            # The first time we list from storage, concurrently "upload"
            # pkgs[2]
            if len(return_values) == 2:
                pkg = make_package("mypkg3", factory=DynamoPackage)
                pkgs.append(pkg)
                self.db.save(pkg)
            return return_values.pop(0)()

        self.storage.list.side_effect = list_storage

        self.db.reload_from_storage()
        all_pkgs = self.engine.scan(DynamoPackage).all()
        self.assertItemsEqual(all_pkgs, pkgs[1:])
        self.assertEqual(self.engine.scan(PackageSummary).count(), 2)

    def test_remove_extra_concurrent_deletes(self):
        """ Remove packages from cache that were concurrently deleted """
        pkgs = [
            make_package(factory=DynamoPackage),
            make_package("mypkg2", factory=DynamoPackage),
        ]
        self.db.save(pkgs[0])

        # Return first pkgs[:], then pkgs[:1] because the second time we list
        # we will have "deleted" pkgs[1]
        return_values = [pkgs[:], pkgs[:1]]
        self.storage.list.side_effect = lambda _: return_values.pop(0)

        self.db.reload_from_storage()
        all_pkgs = self.engine.scan(DynamoPackage).all()
        self.assertItemsEqual(all_pkgs, pkgs[:1])
        self.assertEqual(self.engine.scan(PackageSummary).count(), 1)

    def test_add_missing_more_recent(self):
        """ If we sync a more recent package, update the summary """
        pkgs = [
            make_package(
                last_modified=datetime.utcnow() - timedelta(hours=1),
                factory=DynamoPackage,
            ),
            make_package(version="1.5", factory=DynamoPackage),
        ]
        self.db.save(pkgs[0])
        self.storage.list.return_value = pkgs
        self.db.reload_from_storage()
        all_pkgs = self.engine.scan(DynamoPackage).all()
        self.assertItemsEqual(all_pkgs, pkgs)
        summaries = self.db.summary()
        self.assertEqual(len(summaries), 1)
        summary = summaries[0]
        self.assertEqual(summary["last_modified"], pkgs[1].last_modified)


class TestRedisCache(unittest.TestCase):

    """ Tests for the RedisCache """

    @classmethod
    def setUpClass(cls):
        super(TestRedisCache, cls).setUpClass()
        settings = {
            "pypi.storage": "tests.DummyStorage",
            "db.url": "redis://localhost",
            "db.graceful_reload": True,
        }
        cls.kwargs = RedisCache.configure(settings)
        cls.redis = cls.kwargs["db"]

        try:
            cls.redis.flushdb()
        except redis.exceptions.ConnectionError:
            msg = "Redis not found on port 6379"
            setattr(cls, "setUp", lambda cls: unittest.TestCase.skipTest(cls, msg))

    @classmethod
    def tearDownClass(cls):
        super(TestRedisCache, cls).tearDownClass()

    def setUp(self):
        super(TestRedisCache, self).setUp()
        self.db = RedisCache(DummyRequest(), **self.kwargs)
        self.storage = self.db.storage = MagicMock(spec=IStorage)

    def tearDown(self):
        super(TestRedisCache, self).tearDown()
        self.redis.flushdb()

    def _save_pkgs(self, *pkgs):
        """ Save packages to the db """
        pipe = self.redis.pipeline()
        for pkg in pkgs:
            self.db.save(pkg, pipe)
        pipe.execute()

    def test_add_missing(self):
        """ Add missing packages to cache """
        keys = [make_package()]
        self.storage.list.return_value = keys
        self.db.reload_from_storage()
        all_pkgs = self.db._load_all_packages()
        self.assertItemsEqual(all_pkgs, keys)
        self.assertEqual(len(self.db.summary()), 1)

    def test_remove_extra(self):
        """ Remove extra packages from cache """
        keys = [make_package(), make_package("mypkg2", "1.3.4")]
        self.db.save(keys[0])
        self.db.save(keys[1])
        self.storage.list.return_value = keys[:1]
        self.db.reload_from_storage()
        all_pkgs = self.db._load_all_packages()
        self.assertItemsEqual(all_pkgs, keys[:1])
        # It should have removed the summary as well
        self.assertEqual(len(self.db.summary()), 1)

    def test_remove_extra_leave_concurrent(self):
        """ Removing extra packages will leave packages that were uploaded concurrently """
        pkgs = [make_package(), make_package("mypkg2")]
        self.db.save(pkgs[0])
        self.db.save(pkgs[1])

        # Return first pkgs[1], then pkgs[1:] because the second time we list
        # we will have "uploaded" pkgs[2]
        return_values = [lambda: pkgs[1:2], lambda: pkgs[1:]]

        def list_storage(factory):
            """ mocked method for listing storage packages """
            # The first time we list from storage, concurrently "upload"
            # pkgs[2]
            if len(return_values) == 2:
                pkg = make_package("mypkg3")
                pkgs.append(pkg)
                self.db.save(pkg)
            return return_values.pop(0)()

        self.storage.list.side_effect = list_storage

        self.db.reload_from_storage()
        all_pkgs = self.db._load_all_packages()
        self.assertItemsEqual(all_pkgs, pkgs[1:])
        self.assertEqual(len(self.db.summary()), 2)

    def test_remove_extra_concurrent_deletes(self):
        """ Remove packages from cache that were concurrently deleted """
        pkgs = [make_package(), make_package("mypkg2")]
        self.db.save(pkgs[0])

        # Return first pkgs[:], then pkgs[:1] because the second time we list
        # we will have "deleted" pkgs[1]
        return_values = [pkgs[:], pkgs[:1]]
        self.storage.list.side_effect = lambda _: return_values.pop(0)

        self.db.reload_from_storage()
        all_pkgs = self.db._load_all_packages()
        self.assertItemsEqual(all_pkgs, pkgs[:1])
        self.assertEqual(len(self.db.summary()), 1)

    def test_add_missing_more_recent(self):
        """ If we sync a more recent package, update the summary """
        pkgs = [
            make_package(last_modified=datetime.utcnow() - timedelta(hours=1)),
            make_package(version="1.5"),
        ]
        self.db.save(pkgs[0])
        self.storage.list.return_value = pkgs
        self.db.reload_from_storage()
        all_pkgs = self.db._load_all_packages()
        self.assertItemsEqual(all_pkgs, pkgs)
        summaries = self.db.summary()
        self.assertEqual(len(summaries), 1)
        summary = summaries[0]
        self.assertEqual(summary["last_modified"].hour, pkgs[1].last_modified.hour)


class TestSQLiteCache(unittest.TestCase):

    """ Tests for the SQLCache """

    DB_URL = "sqlite://"

    @classmethod
    def setUpClass(cls):
        super(TestSQLiteCache, cls).setUpClass()
        settings = {
            "pypi.storage": "tests.DummyStorage",
            "db.url": cls.DB_URL,
            "db.graceful_reload": True,
        }
        try:
            cls.kwargs = SQLCache.configure(settings)
        except OperationalError:
            raise unittest.SkipTest("Couldn't connect to database")

    def setUp(self):
        super(TestSQLiteCache, self).setUp()
        transaction.begin()
        self.request = DummyRequest()
        self.request.tm = transaction.manager
        self.db = SQLCache(self.request, **self.kwargs)
        self.sql = self.db.db
        self.storage = self.db.storage = MagicMock(spec=IStorage)

    def tearDown(self):
        super(TestSQLiteCache, self).tearDown()
        transaction.abort()
        self.sql.query(SQLPackage).delete()
        transaction.commit()
        self.request._process_finished_callbacks()

    def _make_package(self, *args, **kwargs):
        """ Wrapper around make_package """
        # Some SQL dbs are rounding the timestamps (looking at you MySQL >:|
        # which is a problem if they round UP to the future, as our
        # calculations depend on the timestamps being monotonically increasing.
        now = datetime.utcnow() - timedelta(seconds=1)
        kwargs.setdefault("last_modified", now)
        kwargs.setdefault("factory", SQLPackage)
        return make_package(*args, **kwargs)

    def test_add_missing(self):
        """ Add missing packages to cache """
        keys = [self._make_package()]
        self.storage.list.return_value = keys
        self.db.reload_from_storage()
        all_pkgs = self.sql.query(SQLPackage).all()
        self.assertItemsEqual(all_pkgs, keys)

    def test_remove_extra(self):
        """ Remove extra packages from cache """
        keys = [self._make_package(), self._make_package("mypkg2", "1.3.4")]
        self.db.save(keys[0])
        self.db.save(keys[1])
        self.storage.list.return_value = keys[:1]
        self.db.reload_from_storage()
        all_pkgs = self.sql.query(SQLPackage).all()
        self.assertItemsEqual(all_pkgs, keys[:1])

    def test_remove_extra_leave_concurrent(self):
        """ Removing extra packages will leave packages that were uploaded concurrently """
        pkgs = [self._make_package(), self._make_package("mypkg2")]
        self.db.save(pkgs[0])
        self.db.save(pkgs[1])

        # Return first pkgs[1], then pkgs[1:] because the second time we list
        # we will have "uploaded" pkgs[2]
        return_values = [lambda: pkgs[1:2], lambda: pkgs[1:]]

        def list_storage(factory):
            """ mocked method for listing storage packages """
            # The first time we list from storage, concurrently "upload"
            # pkgs[2]
            if len(return_values) == 2:
                nowish = datetime.utcnow() + timedelta(seconds=1)
                pkg = self._make_package("mypkg3", last_modified=nowish)
                pkgs.append(pkg)
                self.db.save(pkg)
            return return_values.pop(0)()

        self.storage.list.side_effect = list_storage

        self.db.reload_from_storage()
        all_pkgs = self.sql.query(SQLPackage).all()
        self.assertItemsEqual(all_pkgs, pkgs[1:])

    def test_remove_extra_concurrent_deletes(self):
        """ Remove packages from cache that were concurrently deleted """
        pkgs = [self._make_package(), self._make_package("mypkg2")]
        self.db.save(pkgs[0])

        # Return first pkgs[:], then pkgs[:1] because the second time we list
        # we will have "deleted" pkgs[1]
        return_values = [pkgs[:], pkgs[:1]]
        self.storage.list.side_effect = lambda _: return_values.pop(0)

        self.db.reload_from_storage()
        all_pkgs = self.sql.query(SQLPackage).all()
        self.assertItemsEqual(all_pkgs, pkgs[:1])

    def test_add_missing_more_recent(self):
        """ If we sync a more recent package, update the summary """
        pkgs = [
            self._make_package(last_modified=datetime.utcnow() - timedelta(hours=1)),
            self._make_package(version="1.5"),
        ]
        self.db.save(pkgs[0])
        self.storage.list.return_value = pkgs
        self.db.reload_from_storage()
        all_pkgs = self.sql.query(SQLPackage).all()
        self.assertItemsEqual(all_pkgs, pkgs)


class TestMySQLCache(TestSQLiteCache):
    """ Test the SQLAlchemy cache on a MySQL DB """

    DB_URL = "mysql://root@127.0.0.1:3306/test?charset=utf8mb4"


class TestPostgresCache(TestSQLiteCache):
    """ Test the SQLAlchemy cache on a Postgres DB """

    DB_URL = "postgresql://postgres@127.0.0.1:5432/postgres"
