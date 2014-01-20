""" Caching database implementations """
import os
from datetime import datetime

import logging
import transaction
from pkg_resources import parse_version
from pyramid.path import DottedNameResolver
from pyramid.settings import asbool
from sqlalchemy import engine_from_config, distinct
from sqlalchemy.orm import sessionmaker
# pylint: disable=F0401,E0611
from zope.sqlalchemy import ZopeTransactionExtension
# pylint: enable=F0401,E0611

from .models import create_schema, Package, SQLPackage, normalize_name


LOG = logging.getLogger(__name__)


class ICache(object):

    """ Interface for a caching database that stores package metadata """

    dbtype = None
    autocommit = True
    package_class = Package
    storage_impl = None

    def __init__(self, request=None):
        self.request = request
        self.storage = self.storage_impl(request)

    @classmethod
    def reload_if_needed(cls):
        """
        Reload packages from storage backend if cache is empty

        This will be called when the server first starts

        """
        cache = cls()
        if len(cache.distinct()) == 0:
            LOG.info("Cache is empty. Rebuilding from S3...")
            cache.reload_from_storage()
            LOG.info("Cache repopulated")
        return cache

    @classmethod
    def configure(cls, config):
        """ Configure the cache method with app settings """
        settings = config.get_settings()
        resolver = DottedNameResolver(__name__)
        storage = settings.get('pypi.storage', 'file')
        if storage == 's3':
            storage = 'pypicloud.storage.S3Storage'
        elif storage == 'file':
            storage = 'pypicloud.storage.FileStorage'
        storage_impl = resolver.resolve(storage)
        storage_impl.configure(config)
        cls.storage_impl = storage_impl

        cls.allow_overwrite = asbool(settings.get('pypi.allow_overwrite',
                                                  False))

    def get_url(self, package):
        """ Pass through to storage """
        url = package.url
        new_url = self.storage.get_url(package)
        if self.autocommit and url != new_url:
            self.save(package)
        return new_url

    def download_response(self, package):
        """ Pass through to storage """
        return self.storage.download_response(package)

    def reload_from_storage(self):
        """ Make sure local database is populated with packages """
        self.clear_all()
        packages = self.storage.list(self.package_class)
        for pkg in packages:
            self.save(pkg)

    @staticmethod
    def normalize_name(name):
        """ Normalize a python package name """
        return normalize_name(name)

    def upload(self, name, version, filename, data):
        """ Save this package to the storage mechanism and to the cache """
        name = self.normalize_name(name)
        filename = os.path.basename(filename)
        old_pkg = self.fetch(name, version)
        if old_pkg is not None and not self.allow_overwrite:
            raise ValueError("Package '%s==%s' already exists!" %
                             (name, version))
        path = self.storage.upload(name, version, filename, data)
        new_pkg = self.package_class(name, version, path, datetime.utcnow())
        # If we're overwriting the same package but with a different path,
        # delete the old path
        if old_pkg is not None and new_pkg.path != old_pkg.path:
            self.storage.delete(old_pkg.path)
        self.save(new_pkg)
        return new_pkg

    def delete(self, package):
        """ Delete this package from the database and from storage """
        self.storage.delete(package.path)
        self.clear(package)

    def fetch(self, name, version):
        """ Get matching package if it exists """
        return self._fetch(self.normalize_name(name), version)

    def _fetch(self, name, version):
        """ Override this method to implement 'fetch' """
        raise NotImplementedError

    def all(self, name):
        """ Search for all versions of a package """
        if name is not None:
            name = self.normalize_name(name)
        return self._all(name)

    def _all(self, name):
        """ Override this method to implement 'all' """
        raise NotImplementedError

    def distinct(self):
        """ Get all distinct package names """
        raise NotImplementedError

    def summary(self):
        """
        Summarize package metadata

        Returns
        -------
        packages : list
            List of package dicts, each of which contains 'name', 'stable',
            'unstable', and 'last_modified'.

        """
        packages = []
        for name in self.distinct():
            pkg = {
                'name': name,
                'stable': None,
                'unstable': '0',
                'last_modified': datetime.fromtimestamp(0),
            }
            for package in self.all(name):
                if not package.is_prerelease:
                    if pkg['stable'] is None:
                        pkg['stable'] = package.version
                    else:
                        pkg['stable'] = max(pkg['stable'], package.version,
                                            key=parse_version)
                pkg['unstable'] = max(pkg['unstable'], package.version,
                                      key=parse_version)
                pkg['last_modified'] = max(pkg['last_modified'],
                                           package.last_modified)
            packages.append(pkg)

        return packages

    def clear(self, package):
        """ Remove this package from the caching database """
        raise NotImplementedError

    def clear_all(self):
        """ Clear all cached packages from the database """
        raise NotImplementedError

    def save(self, package):
        """ Save this package to the database """
        raise NotImplementedError


class SQLCache(ICache):

    """ Caching database that uses SQLAlchemy """
    dbtype = 'sql'
    autocommit = False
    package_class = SQLPackage
    dbmaker = None

    def __init__(self, request=None):
        super(SQLCache, self).__init__(request)
        self.db = self.dbmaker()

        if request is not None:
            def cleanup(_):
                """ Close the session after the request """
                self.db.close()
            request.add_finished_callback(cleanup)

    @classmethod
    def reload_if_needed(cls):
        cache = super(SQLCache, cls).reload_if_needed()
        transaction.commit()
        cache.db.close()

    @classmethod
    def configure(cls, config):
        super(SQLCache, cls).configure(config)
        settings = config.get_settings()
        engine = engine_from_config(settings, prefix='db.')
        cls.dbmaker = sessionmaker(
            bind=engine, extension=ZopeTransactionExtension())
        # Create SQL schema if not exists
        create_schema(engine)

    def _fetch(self, name, version):
        return self.db.query(SQLPackage).filter_by(name=name,
                                                   version=version).first()

    def _all(self, name):
        pkgs = self.db.query(SQLPackage).filter_by(name=name).all()
        pkgs.sort(reverse=True)
        return pkgs

    def distinct(self):
        names = self.db.query(distinct(SQLPackage.name))\
            .order_by(SQLPackage.name).all()
        return [n[0] for n in names]

    def summary(self):
        packages = {}
        for package in self.db.query(SQLPackage):
            pkg = packages.get(package.name)
            if pkg is None:
                pkg = {
                    'name': package.name,
                    'stable': None,
                    'unstable': '0',
                    'last_modified': datetime.fromtimestamp(0),
                }
                packages[package.name] = pkg
            if not package.is_prerelease:
                if pkg['stable'] is None:
                    pkg['stable'] = package.version
                else:
                    pkg['stable'] = max(pkg['stable'], package.version,
                                        key=parse_version)
            pkg['unstable'] = max(pkg['unstable'], package.version,
                                  key=parse_version)
            pkg['last_modified'] = max(pkg['last_modified'],
                                       package.last_modified)

        return packages.values()

    def clear(self, package):
        self.db.delete(package)

    def clear_all(self):
        self.db.query(SQLPackage).delete()

    def save(self, package):
        self.db.add(package)


class RedisCache(ICache):

    """ Caching database that uses redis """
    dbtype = 'redis'
    redis_prefix = 'pypicloud:'

    @classmethod
    def configure(cls, config):
        super(RedisCache, cls).configure(config)
        settings = config.get_settings()
        try:
            from redis import StrictRedis
        except ImportError:  # pragma: no cover
            raise ImportError("You must 'pip install redis' before using "
                              "redis as the database")
        db_url = settings.get('db.url')
        cls.db = StrictRedis.from_url(db_url)

    def redis_key(self, package):
        """ Get a unique key for redis """
        return self._redis_key(package.name, package.version)

    def _redis_key(self, name, version):
        """ Get the key to a redis hash that stores a package """
        return "%s%s==%s" % (self.redis_prefix, name, version)

    @property
    def redis_set(self):
        """ Get the key to the redis set of package names """
        return self.redis_prefix + 'set'

    def redis_version_set(self, name):
        """ Get the key to a redis set of versions for a package """
        return "%sset:%s" % (self.redis_prefix, name)

    def reload_from_storage(self):
        self.clear_all()
        packages = self.storage.list(self.package_class)
        pipe = self.db.pipeline()
        for pkg in packages:
            self.save(pkg, pipe=pipe)
        pipe.execute()

    def _fetch(self, name, version):
        data = self.db.hgetall(self._redis_key(name, version))
        if not data:
            return None
        return self._load(data)

    def _load(self, data):
        """ Load a Package class from redis data """
        data['last_modified'] = datetime.fromtimestamp(
            float(data['last_modified']))
        if data.get('expire'):
            data['expire'] = datetime.fromtimestamp(float(data['expire']))

        return self.package_class(**data)

    def _all(self, name):
        versions = self.db.smembers(self.redis_version_set(name))
        pipe = self.db.pipeline()
        for version in versions:
            pipe.hgetall(self._redis_key(name, version))
        packages = [self._load(data) for data in pipe.execute()]
        packages.sort(reverse=True)
        return packages

    def distinct(self):
        return list(self.db.smembers(self.redis_set))

    def clear(self, package):
        del self.db[self.redis_key(package)]
        self.db.srem(self.redis_version_set(package.name), package.version)
        if self.db.scard(self.redis_version_set(package.name)) == 0:
            self.db.srem(self.redis_set, package.name)

    def clear_all(self):
        keys = self.db.keys(self.redis_prefix + '*')
        if keys:
            self.db.delete(*keys)

    def save(self, package, pipe=None):
        if pipe is None:
            pipe = self.db
        data = {
            'name': package.name,
            'version': package.version,
            'path': package.path,
            'last_modified': package.last_modified.strftime('%s.%f'),
        }
        if package.url is not None:
            data['url'] = package.url
        if package.expire is not None:
            data['expire'] = package.expire.strftime('%s.%f')
        pipe.hmset(self.redis_key(package), data)
        pipe.sadd(self.redis_set, package.name)
        pipe.sadd(self.redis_version_set(package.name), package.version)
