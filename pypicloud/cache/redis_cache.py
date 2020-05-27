""" Store package data in redis """
import calendar
import json
import logging
from collections import defaultdict
from datetime import datetime

from pyramid.settings import asbool

from .base import ICache

LOG = logging.getLogger(__name__)


def summary_from_package(package):
    """ Create a summary dict from a package """
    return {
        "name": package.name,
        "summary": package.summary or "",
        "last_modified": package.last_modified,
    }


class RedisCache(ICache):

    """ Caching database that uses redis """

    redis_prefix = "pypicloud:"

    def __init__(self, request=None, db=None, graceful_reload=False, **kwargs):
        super(RedisCache, self).__init__(request, **kwargs)
        self.db = db
        self.graceful_reload = graceful_reload

    @classmethod
    def configure(cls, settings):
        kwargs = super(RedisCache, cls).configure(settings)
        try:
            from redis import StrictRedis
        except ImportError:  # pragma: no cover
            raise ImportError(
                "You must 'pip install redis' before using " "redis as the database"
            )
        kwargs["graceful_reload"] = asbool(settings.get("db.graceful_reload", False))
        db_url = settings.get("db.url")
        kwargs["db"] = StrictRedis.from_url(db_url, decode_responses=True)
        return kwargs

    def redis_key(self, key):
        """ Get the key to a redis hash that stores a package """
        return "%spackage:%s" % (self.redis_prefix, key)

    @property
    def redis_set(self):
        """ Get the key to the redis set of package names """
        return self.redis_prefix + "set"

    def redis_filename_set(self, name):
        """ Get the key to a redis set of filenames for a package """
        return "%sset:%s" % (self.redis_prefix, name)

    def redis_summary_key(self, name):
        """ Get the redis key to a summary for a package """
        return "%ssummary:%s" % (self.redis_prefix, name)

    def fetch(self, filename):
        data = self.db.hgetall(self.redis_key(filename))
        if not data:
            return None
        return self._load(data)

    def _load(self, data):
        """ Load a Package class from redis data """
        name = data.pop("name")
        version = data.pop("version")
        filename = data.pop("filename")
        last_modified = datetime.utcfromtimestamp(float(data.pop("last_modified")))
        summary = data.pop("summary")
        if summary == "":
            summary = None
        kwargs = dict(((k, json.loads(v)) for k, v in data.items()))
        return self.new_package(
            name, version, filename, last_modified, summary, **kwargs
        )

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
        return self._load_summaries(self.db.smembers(self.redis_set))

    def _load_summaries(self, package_names):
        """ Load summaries for provided package names """
        pipe = self.db.pipeline()
        for name in package_names:
            pipe.hgetall(self.redis_summary_key(name))
        summaries = [s for s in pipe.execute() if s]
        for summary in summaries:
            if summary.get("summary", "") == "":
                summary["summary"] = None
            summary["last_modified"] = datetime.utcfromtimestamp(
                float(summary["last_modified"])
            )
        return summaries

    def clear(self, package):
        count = self._delete_package(package)
        if count == 0:
            self._delete_summary(package.name)

    def _delete_package(self, package, pipe=None):
        """ Delete package keys from redis """
        should_execute = False
        if pipe is None:
            should_execute = True
            pipe = self.db.pipeline()
        pipe.delete(self.redis_key(package.filename))
        pipe.srem(self.redis_filename_set(package.name), package.filename)
        if should_execute:
            pipe.scard(self.redis_filename_set(package.name))
            return pipe.execute()[2]

    def _delete_summary(self, package_name, pipe=None):
        """ Delete summary keys from redis """
        should_execute = False
        if pipe is None:
            should_execute = True
            pipe = self.db.pipeline()
        pipe.srem(self.redis_set, package_name)
        pipe.delete(self.redis_summary_key(package_name))
        if should_execute:
            pipe.execute()

    def clear_all(self):
        keys = self.db.keys(self.redis_prefix + "*")
        if keys:
            self.db.delete(*keys)

    def save(self, package, pipe=None, save_summary=True):
        should_execute = False
        if pipe is None:
            pipe = self.db.pipeline()
            should_execute = True
        dt = package.last_modified
        last_modified = calendar.timegm(dt.utctimetuple()) + dt.microsecond / 1000000.0
        data = {
            "name": package.name,
            "version": package.version,
            "filename": package.filename,
            "last_modified": last_modified,
            "summary": package.summary or "",
        }
        for key, value in package.data.items():
            data[key] = json.dumps(value)
        pipe.hmset(self.redis_key(package.filename), data)
        pipe.sadd(self.redis_set, package.name)
        pipe.sadd(self.redis_filename_set(package.name), package.filename)
        if save_summary:
            self._save_summary(summary_from_package(package), pipe)
        if should_execute:
            pipe.execute()

    def _save_summary(self, summary, pipe):
        """ Save a summary dict to redis """
        dt = summary["last_modified"]
        last_modified = calendar.timegm(dt.utctimetuple()) + dt.microsecond / 1000000.0
        pipe.hmset(
            self.redis_summary_key(summary["name"]),
            {
                "name": summary["name"],
                "summary": summary["summary"] or "",
                "last_modified": last_modified,
            },
        )

    def _load_all_packages(self):
        """ Load all packages that are in redis """
        pipe = self.db.pipeline()
        for filename_key in self.db.keys(self.redis_key("*")):
            pipe.hgetall(filename_key)
        return [self._load(data) for data in pipe.execute() if data]

    def reload_from_storage(self, clear=True):
        if not self.graceful_reload:
            if clear:
                self.clear_all()
            packages = self.storage.list(self.new_package)
            pipe = self.db.pipeline()
            for pkg in packages:
                self.save(pkg, pipe=pipe)
            pipe.execute()
            return

        LOG.info("Rebuilding cache from storage")
        # Log start time
        start = datetime.utcnow()
        # Fetch packages from storage s1
        s1 = set(self.storage.list(self.new_package))
        # Fetch cache packages c1
        c1 = set(self._load_all_packages())

        # Add missing packages to cache (s1 - c1)
        missing = s1 - c1
        if missing:
            LOG.info("Adding %d missing packages to cache", len(missing))
            pipe = self.db.pipeline()
            for package in missing:
                self.save(package, pipe, save_summary=False)
            pipe.execute()

        # Delete extra packages from cache (c1 - s1) when last_modified < start
        # The time filter helps us avoid deleting packages that were
        # concurrently uploaded.
        extra1 = [p for p in (c1 - s1) if p.last_modified < start]
        if extra1:
            LOG.info("Removing %d extra packages from cache", len(extra1))
            pipe = self.db.pipeline()
            for package in extra1:
                self._delete_package(package, pipe)
            pipe.execute()

        # If any packages were concurrently deleted during the cache rebuild,
        # we can detect them by polling storage again and looking for any
        # packages that were present in s1 and are missing from s2
        s2 = set(self.storage.list(self.new_package))
        # Delete extra packages from cache (s1 - s2)
        extra2 = s1 - s2
        if extra2:
            LOG.info(
                "Removing %d packages from cache that were concurrently "
                "deleted during rebuild",
                len(extra2),
            )
            pipe = self.db.pipeline()
            for package in extra2:
                self._delete_package(package, pipe)
            pipe.execute()
            # Remove these concurrently-deleted files from the list of packages
            # that were missing from the cache. Don't want to use those to
            # update the summaries below.
            missing -= extra2

        # Update the summary for added packages
        packages_by_name = defaultdict(list)
        for package in missing:
            package.last_modified = package.last_modified
            packages_by_name[package.name].append(package)

        summaries = self._load_summaries(packages_by_name.keys())
        summaries_by_name = {}
        for summary in summaries:
            summaries_by_name[summary["name"]] = summary
        for name, packages in packages_by_name.items():
            if name in summaries_by_name:
                summary = summaries_by_name[name]
            else:
                summary = summary_from_package(packages[0])
                summaries.append(summary)
            for package in packages:
                if package.last_modified > summary["last_modified"]:
                    summary["last_modified"] = package.last_modified
                    summary["summary"] = package.summary
        if summaries:
            LOG.info("Updating %d package summaries", len(summaries))
            pipe = self.db.pipeline()
            for summary in summaries:
                self._save_summary(summary, pipe)
            pipe.execute()

        # Remove the PackageSummary for deleted packages
        removed = set()
        for package in extra1:
            removed.add(package.name)
        for package in extra2:
            removed.add(package.name)
        if removed:
            pipe = self.db.pipeline()
            for name in removed:
                pipe.scard(self.redis_filename_set(name))
            counts = pipe.execute()
            pipe = self.db.pipeline()
            for name, count in zip(removed, counts):
                if count == 0:
                    self._delete_summary(name, pipe)
            pipe.execute()

    def check_health(self):
        from redis import RedisError

        try:
            self.db.echo("ok")
        except RedisError as e:
            return (False, str(e))
        else:
            return (True, "")
