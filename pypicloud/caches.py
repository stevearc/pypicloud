""" Cache implementations for storing S3 urls """
import time

import shelve


class ICache(object):

    """ Cache interface for caching the S3 urls """

    def store(self, request, key, obj, expire_after):
        """
        Store a file's generated url and expire time

        Parameters
        ----------
        request : :class:`~pyramid.request.Request`
        key : str
            The path of the S3 file
        obj : str
            The generated url
        expire_after : float
            Unix timestamp after which this cache should expire

        """
        raise NotImplementedError

    def fetch(self, request, key):
        """
        Retrieve a cached S3 url

        Parameters
        ----------
        request : :class:`~pyramid.request.Request`
        key : str
            The path of the S3 file

        """
        raise NotImplementedError


class FilesystemCache(ICache):

    """
    Cache implementation that uses the :mod:`shelve` module

    Requires you to define ``cache.container`` in your config file, which is a
    path to a file. For example: "%(here)s/cache"

    """

    def __init__(self, settings):
        super(FilesystemCache, self).__init__()
        self.container = settings['cache.container']
        self.shelf = shelve.open(self.container)

    def store(self, request, key, obj, expire_after):
        self.shelf[str(key)] = (obj, expire_after)
        self.shelf.sync()

    def fetch(self, request, key):
        value = self.shelf.get(str(key))
        if value is None:
            return None
        obj, expire_after = value
        if time.time() < expire_after:
            return obj
        return None


class SqliteDictCache(ICache):

    """
    Cache implementation backed by :mod:`sqlitedict`

    You will need to install the sqlitedict module

    Requires you to define ``cache.url`` in your config file, which is a SQLite
    url. For example: "sqlite:///%(here)s/cache.sqlite"

    """

    def __init__(self, settings):
        super(SqliteDictCache, self).__init__()
        self.url = settings['cache.url']
        from sqlitedict import SqliteDict # pylint: disable=F0401
        self.sqlite = SqliteDict(self.url, autocommit=True)

    def store(self, request, key, obj, expire_after):
        self.sqlite[key] = (obj, expire_after)

    def fetch(self, request, key):
        value = self.sqlite.get(key)
        if value is None:
            return None
        obj, expire_after = value
        if time.time() < expire_after:
            return obj
        return None
