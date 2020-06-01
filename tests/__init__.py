""" Tests for pypicloud """
import os
import unittest
from collections import defaultdict
from datetime import datetime

from mock import MagicMock
from pyramid.testing import DummyRequest

from pypicloud.auth import _is_logged_in
from pypicloud.cache import ICache
from pypicloud.models import Package
from pypicloud.storage import IStorage

unittest.TestCase.assertItemsEqual = unittest.TestCase.assertCountEqual


os.environ["AWS_SECRET_ACCESS_KEY"] = "access_key"
os.environ["AWS_ACCESS_KEY_ID"] = "secret_key"


def make_package(
    name="mypkg",
    version="1.1",
    filename=None,
    last_modified=None,
    summary="summary",
    factory=Package,
    **kwargs
):
    """ Convenience method for constructing a package """
    filename = filename or "%s-%s.tar.gz" % (name, version)
    return factory(
        name, version, filename, last_modified or datetime.utcnow(), summary, **kwargs
    )


def make_dist(
    url=None,
    name="mypkg",
    version="1.0",
    summary="A package summary",
    requires_python=">=3.5",
    digests=None,
):
    url = url or "https://pypi.org/pypi/%s/%s-%s.tar.gz" % (name, name, version)
    return {
        "name": name,
        "version": version,
        "url": url,
        "summary": summary,
        "requires_python": requires_python,
        "digests": digests or {},
    }


class DummyStorage(IStorage):

    """ In-memory implementation of IStorage """

    def __init__(self, request=None):
        super(DummyStorage, self).__init__(request)
        self.packages = {}

    def list(self, factory=Package):
        """ Return a list or generator of all packages """
        for args in self.packages.values():
            yield args[0]

    def download_response(self, package):
        return None

    def upload(self, package, data):
        self.packages[package.filename] = (package, data)

    def delete(self, package):
        del self.packages[package.filename]

    def open(self, package):
        return self.packages[package.filename][1]


class DummyCache(ICache):

    """ In-memory implementation of ICache """

    def __init__(self, request=None, **kwargs):
        kwargs.setdefault("storage", DummyStorage)
        super(DummyCache, self).__init__(request, **kwargs)
        self.packages = defaultdict(dict)

    def fetch(self, filename):
        """ Override this method to implement 'fetch' """
        return self.packages.get(filename)

    def all(self, name):
        """ Override this method to implement 'all' """
        return [p for p in self.packages.values() if p.name == name]

    def distinct(self):
        """ Get all distinct package names """
        return list(set((p.name for p in self.packages.values())))

    def clear(self, package):
        """ Remove this package from the caching database """
        del self.packages[package.filename]

    def clear_all(self):
        """ Clear all cached packages from the database """
        self.packages.clear()

    def save(self, package):
        """ Save this package to the database """
        self.packages[package.filename] = package


class MockServerTest(unittest.TestCase):

    """ Base class for tests that need in-memory ICache objects """

    def setUp(self):
        self.request = DummyRequest()
        self.request.registry = MagicMock()
        self.request.userid = None
        self.request.__class__.is_logged_in = property(_is_logged_in)
        self.db = self.request.db = DummyCache(self.request)
        self.request.path_url = "/path/"
        self.request.forbid = MagicMock()
        self.params = {}
        self.request.param = lambda x, y=None: self.params.get(x, y)
