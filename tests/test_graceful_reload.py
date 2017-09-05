""" Tests for gracefully reloading the caches """
import unittest
from mock import MagicMock
from pyramid.testing import DummyRequest

from . import make_package
from pypicloud.cache.dynamo import DynamoCache, DynamoPackage, PackageSummary
from pypicloud.storage import IStorage


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
            'db.region': 'us-east-1',
            'db.host': host,
            'db.port': port,
            'db.namespace': 'test.',
            'db.aws_access_key_id': '',
            'db.aws_secret_access_key': '',
            'db.graceful_reload': True,
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
            summary = PackageSummary(pkg)
            self.engine.save(summary, overwrite=True)

    def test_add_missing(self):
        """ Add missing packages to cache """
        keys = [
            make_package(factory=DynamoPackage),
        ]
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
            make_package('mypkg2', '1.3.4', factory=DynamoPackage),
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
            make_package('mypkg2', factory=DynamoPackage),
        ]
        self.db.save(pkgs[0])
        self.db.save(pkgs[1])

        # Return first pkgs[1], then pkgs[1:] because the second time we list
        # we will have "uploaded" pkgs[2]
        return_values = [lambda: pkgs[1:2], lambda: pkgs[1:]]

        def list_storage(package_class):
            """ mocked method for listing storage packages """
            # The first time we list from storage, concurrently "upload"
            # pkgs[2]
            if len(return_values) == 2:
                pkg = make_package('mypkg3', factory=DynamoPackage)
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
            make_package('mypkg2', factory=DynamoPackage),
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
