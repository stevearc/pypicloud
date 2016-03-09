""" Store package data in DynamoDB """
import logging
import time
from collections import namedtuple
from datetime import datetime
from itertools import imap, chain
from pkg_resources import parse_version

from dynamo3 import ConditionalCheckFailedException, DynamoDBConnection
from pyramid.settings import asbool

from .base import ICache
from pypicloud.models import Package
from pypicloud.util import EPOCH, retry


try:
    from flywheel import Engine, Model, Field, GlobalIndex, __version__
    if parse_version(__version__) < parse_version('0.2.0'):  # pragma: no cover
        raise ValueError("Pypicloud requires flywheel>=0.2.0")
except ImportError:  # pragma: no cover
    raise ImportError("You must 'pip install flywheel' before using "
                      "DynamoDB as the cache database")

LOG = logging.getLogger(__name__)


def _path_depth(package):
    """Count the slashes in path, or return infinity on no path."""
    path = package.data.get('path')
    if not path:
        return float('+inf')
    return path.count('/')


def _decide_between_versions(contender, current):
    """Decide between packages with the same filename on different paths.

    The earliest one wins. If they both have the same last_modified, prefer the
    one closer to the root.
    """

    if contender.last_modified < current.last_modified:
        return contender
    if current.last_modified < contender.last_modified:
        return current

    if _path_depth(contender) < _path_depth(current):
        return contender

    return current


PackageUpdates = namedtuple(
    'PackageUpdates',
    [
        'new_packages',
        'seen_packages',
        'updated_packages',
        'stale_packages',
    ],
)


def calculate_package_updates(
        cache_packages,
        storage_packages,
):
    """ Calculates what changes need to happen in the cache to update it. """

    cached_pkg_by_filename = dict(
        (pkg.filename, pkg,)
        for pkg in cache_packages
    )

    new_packages = set()
    seen_packages = set()
    updated_packages = set()

    for pkg in storage_packages:
        try:
            cached_pkg = cached_pkg_by_filename[pkg.filename]
        except KeyError:
            new_packages.add(pkg)
        else:
            if _decide_between_versions(pkg, cached_pkg) is cached_pkg:
                seen_packages.add(cached_pkg)
            else:
                cached_pkg.name = pkg.name
                cached_pkg.version = pkg.version
                cached_pkg.last_modified = pkg.last_modified
                cached_pkg.data = dict(pkg.data)

                updated_packages.add(cached_pkg)

    stale_packages = set(cached_pkg_by_filename.itervalues()) - seen_packages

    return PackageUpdates(
        new_packages,
        seen_packages,
        updated_packages,
        stale_packages,
    )


class DynamoPackage(Package, Model):

    """ Python package stored in DynamoDB """
    __metadata__ = {
        'global_indexes': [
            GlobalIndex('name-index', 'name'),
        ],
    }
    filename = Field(hash_key=True)
    name = Field()
    version = Field()
    last_modified = Field(data_type=datetime)
    data = Field(data_type=dict)


class PackageSummary(Model):

    """ Aggregate data about packages """
    name = Field(hash_key=True)
    stable = Field()
    unstable = Field()
    last_modified = Field(data_type=datetime)

    def __init__(self, package):
        super(PackageSummary, self).__init__(package.name)
        self.unstable = package.version
        if not package.is_prerelease:
            self.stable = package.version
        self.last_modified = package.last_modified

    def update_with(self, package):
        """ Update summary with a package """
        if self.name != package.name:
            LOG.error("Summary name '%s' doesn't match package name '%s'",
                      self.name, package.name)
            return
        self.unstable = max(self.unstable, package.version, key=parse_version)
        self.last_modified = max(self.last_modified, package.last_modified)
        if not package.is_prerelease:
            if self.stable is None:
                self.stable = package.version
            else:
                self.stable = max(self.stable, package.version,
                                  key=parse_version)


class DynamoCache(ICache):

    """ Caching database that uses DynamoDB """
    package_class = DynamoPackage

    def __init__(self, request=None, engine=None, **kwargs):
        super(DynamoCache, self).__init__(request, **kwargs)
        self.engine = engine

    @classmethod
    def configure(cls, settings):
        kwargs = super(DynamoCache, cls).configure(settings)

        access_key = settings.get('db.access_key')
        secret_key = settings.get('db.secret_key')
        region = settings.get('db.region')
        host = settings.get('db.host')
        port = int(settings.get('db.port', 8000))
        secure = asbool(settings.get('db.secure', False))
        namespace = settings.get('db.namespace', ())

        if region is not None:
            connection = DynamoDBConnection.connect(region,
                                                    access_key=access_key,
                                                    secret_key=secret_key)
        elif host is not None:
            connection = DynamoDBConnection.connect('us-east-1',
                                                    host=host,
                                                    port=port,
                                                    is_secure=secure,
                                                    access_key=access_key,
                                                    secret_key=secret_key)
        else:
            raise ValueError("Must specify either db.region or db.host!")
        kwargs['engine'] = engine = Engine(namespace=namespace,
                                           dynamo=connection)

        engine.register(DynamoPackage, PackageSummary)
        engine.create_schema()
        return kwargs

    def reload_from_storage(self):
        LOG.info("Recalculating package cache.")

        cache_updates = calculate_package_updates(
            self.engine.scan(DynamoPackage),
            self.storage.list(self.package_class),
        )

        LOG.info("Package cache recalculated. Persisting new version.")

        def do_or_skip(operation, coll, warn=True, **kwargs):
            """ Do `operation`, ignore ConditionalCheckFailedException """
            operator = getattr(self.engine, operation)
            for o in coll:
                try:
                    operator(o, **kwargs)
                except ConditionalCheckFailedException:
                    if not warn:
                        continue
                    LOG.warn(
                        "Ignoring consistency problem while trying to %s %r.",
                        operation,
                        o,
                    )

        # If somebody else updated a package, they're probably operating on
        # fresher data. In those cases, skip the change.
        do_or_skip('save', cache_updates.new_packages, overwrite=False, warn=False)
        do_or_skip('sync', cache_updates.updated_packages, raise_on_conflict=True)
        do_or_skip('delete', cache_updates.stale_packages, raise_on_conflict=True)

        LOG.info("Package cache persisted. Updating summaries.")

        all_changed_packages = chain(
            cache_updates.new_packages,
            cache_updates.updated_packages,
            cache_updates.stale_packages,
        )
        for name in set(p.name for p in all_changed_packages):
            self._rebuild_summary_for_package_named(name)

        LOG.info("Summaries updated. All done.")

    def fetch(self, filename):
        return self.engine.get(DynamoPackage, filename=filename)

    def all(self, name):
        return sorted(self.engine.query(DynamoPackage).filter(name=name),
                      reverse=True)

    def distinct(self):
        names = set()
        for summary in self.engine.scan(PackageSummary):
            names.add(summary.name)
        return sorted(names)

    def summary(self):
        summaries = sorted(self.engine.scan(PackageSummary),
                           key=lambda s: s.name)
        return [s.__json__() for s in summaries]

    @retry(tries=3, exceptions=(ConditionalCheckFailedException,))
    def _rebuild_summary_for_package_named(self, name):
        """Rebuild the summary from the cached packages."""

        pkgs = self.all(name)
        summary = self.engine.get(PackageSummary, name=name, consistent=True)

        if not pkgs:
            if summary:
                self.engine.delete(summary)
            return

        if summary:
            summary.stable = None
            summary.unstable = '0'
            summary.last_modified = EPOCH
        else:
            summary = PackageSummary(pkgs[0])

        for pkg in pkgs:
            summary.update_with(pkg)

        self.engine.sync(summary, raise_on_conflict=True)

    def clear(self, package):
        self.engine.delete(package)
        self._rebuild_summary_for_package_named(package.name)

    def clear_all(self):
        # We're replacing the schema, so make sure we save and restore the
        # current table/index throughput
        throughput = {}
        for model in (DynamoPackage, PackageSummary):
            tablename = model.meta_.ddb_tablename(self.engine.namespace)
            desc = self.engine.dynamo.describe_table(tablename)
            tablename = model.meta_.ddb_tablename()
            throughput[tablename] = {
                'read': desc.throughput.read,
                'write': desc.throughput.write,
            }
            for index in desc.global_indexes:
                throughput[tablename][index.name] = {
                    'read': index.throughput.read,
                    'write': index.throughput.write,
                }

        self.engine.delete_schema()
        self.engine.create_schema(throughput=throughput)

    def save(self, package):
        self.engine.save(package)

        summary = self.engine.get(PackageSummary, name=package.name)
        if summary is None:
            summary = PackageSummary(package)
        else:
            summary.update_with(package)
        self.engine.sync(summary)
