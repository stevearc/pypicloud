""" Store package data in redis """
from datetime import datetime

import json

from .base import ICache


class RedisCache(ICache):

    """ Caching database that uses redis """
    redis_prefix = 'pypicloud:'

    def __init__(self, request=None, db=None, **kwargs):
        super(RedisCache, self).__init__(request, **kwargs)
        self.db = db

    @classmethod
    def configure(cls, settings):
        kwargs = super(RedisCache, cls).configure(settings)
        try:
            from redis import StrictRedis
        except ImportError:  # pragma: no cover
            raise ImportError("You must 'pip install redis' before using "
                              "redis as the database")
        db_url = settings.get('db.url')
        kwargs['db'] = StrictRedis.from_url(db_url)
        return kwargs

    def redis_key(self, key):
        """ Get the key to a redis hash that stores a package """
        return "%spackage:%s" % (self.redis_prefix, key)

    @property
    def redis_set(self):
        """ Get the key to the redis set of package names """
        return self.redis_prefix + 'set'

    def redis_filename_set(self, name):
        """ Get the key to a redis set of filenames for a package """
        return "%sset:%s" % (self.redis_prefix, name)

    def reload_from_storage(self):
        self.clear_all()
        packages = self.storage.list(self.package_class)
        pipe = self.db.pipeline()
        for pkg in packages:
            self.save(pkg, pipe=pipe)
        pipe.execute()

    def fetch(self, filename):
        data = self.db.hgetall(self.redis_key(filename))
        if not data:
            return None
        return self._load(data)

    def _load(self, data):
        """ Load a Package class from redis data """
        name = data.pop('name')
        version = data.pop('version')
        filename = data.pop('filename')
        last_modified = datetime.fromtimestamp(
            float(data.pop('last_modified')))
        kwargs = dict(((k, json.loads(v)) for k, v in data.iteritems()))
        return self.package_class(name, version, filename, last_modified,
                                  **kwargs)

    def all(self, name):
        filenames = self.db.smembers(self.redis_filename_set(name))
        pipe = self.db.pipeline()
        for filename in filenames:
            pipe.hgetall(self.redis_key(filename))
        packages = [self._load(data) for data in pipe.execute()]
        packages.sort(reverse=True)
        return packages

    def distinct(self):
        return list(self.db.smembers(self.redis_set))

    def clear(self, package):
        del self.db[self.redis_key(package.filename)]
        self.db.srem(self.redis_filename_set(package.name), package.filename)
        if self.db.scard(self.redis_filename_set(package.name)) == 0:
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
            'filename': package.filename,
            'last_modified': package.last_modified.strftime('%s.%f'),
        }
        for key, value in package.data.iteritems():
            data[key] = json.dumps(value)
        pipe.hmset(self.redis_key(package.filename), data)
        pipe.sadd(self.redis_set, package.name)
        pipe.sadd(self.redis_filename_set(package.name), package.filename)
