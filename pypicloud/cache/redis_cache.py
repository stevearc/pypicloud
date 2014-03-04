""" Store package data in redis """
from datetime import datetime

import json

from .base import ICache


class RedisCache(ICache):

    """ Caching database that uses redis """
    dbtype = 'redis'
    redis_prefix = 'pypicloud:'

    @classmethod
    def configure(cls, settings):
        super(RedisCache, cls).configure(settings)
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
        name = data.pop('name')
        version = data.pop('version')
        path = data.pop('path')
        last_modified = datetime.fromtimestamp(
            float(data.pop('last_modified')))
        kwargs = dict(((k, json.loads(v)) for k, v in data.iteritems()))
        return self.package_class(name, version, path, last_modified, **kwargs)

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
        for key, value in package.data.iteritems():
            data[key] = json.dumps(value)
        pipe.hmset(self.redis_key(package), data)
        pipe.sadd(self.redis_set, package.name)
        pipe.sadd(self.redis_version_set(package.name), package.version)
