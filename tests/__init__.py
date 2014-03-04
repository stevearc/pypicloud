""" Tests for pypicloud """
from mock import MagicMock, patch
from collections import defaultdict
from pypicloud.cache.sql import create_schema
from pypicloud.storage import IStorage
from pypicloud.cache import ICache
from pyramid.testing import DummyRequest
from redis import StrictRedis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime


try:
    import unittest2 as unittest  # pylint: disable=F0401
except ImportError:
    import unittest


class DummyStorage(IStorage):

    """ In-memory implementation of IStorage """

    def __init__(self, request=None):
        super(DummyStorage, self).__init__(request)
        self.packages = {}

    def __call__(self, *args):
        return self

    def list(self, factory):
        """ Return a list or generator of all packages """
        for args in self.packages.itervalues():
            all_args = args + (datetime.utcnow(),)
            yield factory(*all_args)

    def get_url(self, package):
        return package.path, False

    def download_response(self, package):
        return None

    def upload(self, name, version, filename, data):
        self.packages[filename] = (name, version, filename)
        return filename

    def delete(self, path):
        del self.packages[path]

    def reset(self):
        """ Clear all packages """
        self.packages = {}


class DummyCache(ICache):

    """ In-memory implementation of ICache """
    storage_impl = DummyStorage

    def __init__(self, request=None):
        super(DummyCache, self).__init__(request)
        self.packages = defaultdict(dict)

    @classmethod
    def configure(cls, config):
        pass

    def __call__(self, _):
        return self

    def reset(self):
        """ Clear all packages from storage and self """
        self.packages.clear()
        self.storage.reset()

    def _fetch(self, name, version):
        """ Override this method to implement 'fetch' """
        return self.packages[name].get(version)

    def _all(self, name):
        """ Override this method to implement 'all' """
        return self.packages[name].values()

    def distinct(self):
        """ Get all distinct package names """
        return [name for name, versions in self.packages.iteritems()
                if len(versions) > 0]

    def clear(self, package):
        """ Remove this package from the caching database """
        del self.packages[package.name]

    def clear_all(self):
        """ Clear all cached packages from the database """
        self.packages.clear()

    def save(self, package):
        """ Save this package to the database """
        self.packages[package.name][package.version] = package


class MockServerTest(unittest.TestCase):

    """ Base class for tests that need in-memory ICache objects """

    def setUp(self):
        self.request = DummyRequest()
        self.db = self.request.db = DummyCache(self.request)
        self.request.path_url = '/path/'
        self.params = {}
        self.request.param = lambda x: self.params[x]

    def tearDown(self):
        self.request.db.reset()
