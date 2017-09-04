""" Store package data in redis """
from __future__ import unicode_literals

import calendar
import json
import six
from datetime import datetime

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
        kwargs['db'] = StrictRedis.from_url(db_url, decode_responses=True)
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

    def redis_summary_key(self, name):
        """ Get the redis key to a summary for a package """
        return "%ssummary:%s" % (self.redis_prefix, name)

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
        last_modified = datetime.utcfromtimestamp(
            float(data.pop('last_modified')))
        summary = data.pop('summary')
        if summary == '':
            summary = None
        kwargs = dict(((k, json.loads(v)) for k, v in six.iteritems(data)))
        return self.package_class(name, version, filename, last_modified,
                                  summary, **kwargs)

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

    def summary(self):
        pipe = self.db.pipeline()
        for name in self.db.smembers(self.redis_set):
            pipe.hgetall(self.redis_summary_key(name))
        summaries = pipe.execute()
        for summary in summaries:
            if summary['summary'] == '':
                summary['summary'] = None
            summary['last_modified'] = datetime.utcfromtimestamp(
                float(summary['last_modified'])
            )
        return summaries

    def clear(self, package):
        pipe = self.db.pipeline()
        pipe.delete(self.redis_key(package.filename))
        pipe.srem(self.redis_filename_set(package.name), package.filename)
        pipe.scard(self.redis_filename_set(package.name))
        count = pipe.execute()[2]
        if count == 0:
            pipe = self.db.pipeline()
            pipe.srem(self.redis_set, package.name)
            pipe.delete(self.redis_summary_key(package.name))
            pipe.execute()

    def clear_all(self):
        keys = self.db.keys(self.redis_prefix + '*')
        if keys:
            self.db.delete(*keys)

    def save(self, package, pipe=None):
        should_execute = False
        if pipe is None:
            pipe = self.db.pipeline()
            should_execute = True
        dt = package.last_modified
        last_modified = (calendar.timegm(dt.utctimetuple()) +
                         dt.microsecond / 1000000.0)
        data = {
            'name': package.name,
            'version': package.version,
            'filename': package.filename,
            'last_modified': last_modified,
            'summary': package.summary or '',
        }
        for key, value in six.iteritems(package.data):
            data[key] = json.dumps(value)
        pipe.hmset(self.redis_key(package.filename), data)
        pipe.sadd(self.redis_set, package.name)
        pipe.sadd(self.redis_filename_set(package.name), package.filename)
        pipe.hmset(self.redis_summary_key(package.name), {
            'name': package.name,
            'summary': package.summary or '',
            'last_modified': last_modified,
        })
        if should_execute:
            pipe.execute()
