""" Store package data in DynamoDB """
import logging
import time
from collections import namedtuple
from datetime import datetime
from itertools import imap
from pkg_resources import parse_version

from dynamo3 import ConditionalCheckFailedException, DynamoDBConnection
from pyramid.settings import asbool

from .base import ICache
from pypicloud.models import Package
from pypicloud.util import EPOCH


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


def _clear_summary(summary):

    """ Clear out the field of a PackageSummary object """
    summary.stable = None
    summary.unstable = '0'
    summary.last_modified = EPOCH
    return summary


CacheUpdates = namedtuple(
    'CacheUpdates',
    [
        'new_packages',
        'seen_packages',
        'stale_packages',
        'new_summaries',
        'seen_summaries',
        'stale_summaries',
    ],
)


def calculate_cache_updates(
    cache_packages,
    cache_summaries,
    storage_packages,
    summary_factory,
):

    """ Calculates what changes need to happen in the cache to update it. """

    cached_pkg_by_filename = dict(
        (pkg.filename, pkg,)
        for pkg in cache_packages
    )
    # Clear out non-key fields of the cached summaries to purge stable and
    # unstable fields.
    cached_summ_by_name = dict(
        (summ.name, _clear_summary(summ),)
        for summ in cache_summaries
    )

    new_packages = set()
    seen_packages = set()
    stale_packages = set()

    new_summaries_by_name = dict()
    seen_summaries = set()

    for pkg in storage_packages:
        try:
            summ = cached_summ_by_name[pkg.name]
        except KeyError:
            summ = new_summaries_by_name.setdefault(
                pkg.name,
                summary_factory(pkg),
            )
        else:
            seen_summaries.add(summ)

        try:
            cached_pkg = cached_pkg_by_filename[pkg.filename]
        except KeyError:
            new_packages.add(pkg)
            summ.update_with(pkg)
        else:
            if _decide_between_versions(
                pkg,
                cached_pkg,
            ) is pkg:
                cached_pkg.filename = pkg.filename
                cached_pkg.name = pkg.name
                cached_pkg.version = pkg.version
                cached_pkg.last_modified = pkg.last_modified
                cached_pkg.data = dict(pkg.data)

            seen_packages.add(cached_pkg)
            summ.update_with(cached_pkg)

    stale_packages = set(cached_pkg_by_filename.itervalues()) - seen_packages

    new_summaries = new_summaries_by_name.itervalues()
    stale_summaries = set(cached_summ_by_name.itervalues()) - seen_summaries

    return CacheUpdates(
        new_packages,
        seen_packages,
        stale_packages,
        new_summaries,
        seen_summaries,
        stale_summaries,
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
        LOG.info("Recalculating cache.")

        cache_updates = calculate_cache_updates(
            self.engine.scan(DynamoPackage),
            self.engine.scan(PackageSummary),
            self.storage.list(self.package_class),
            PackageSummary,
        )

        # HACK flywheel only checks for dirtyness on the first difference.
        # If we do:
        #     obj.a, obj.b = obj.b, obj.a
        #     obj.a, obj.b = obj.b, obj.a
        # We're going to get:
        #     bool(obj.__dirty__) == True
        def is_effectively_dirty(o):
            """ Confirm that the fields marked on __dirty__ are true """
            return any(
                o.ddb_dump_cached_(f) != o.ddb_dump_field_(f)
                for f in o.__dirty__ | set(o.__cache__.keys())
            )
        updated_packages = filter(is_effectively_dirty, cache_updates.seen_packages)
        updated_summaries = filter(is_effectively_dirty, cache_updates.seen_summaries)

        LOG.info("Cache recalculated. Persisting new version.")

        def do_or_skip(operation, coll, warn=True, **kwargs):
            """ Do `operation`, ignore ConditionalCheckFailedExceptions """
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

        def do_or_recalc_summaries(operation, coll, **kwargs):
            """ Do `operation`, on ConditionalCheckFailedExceptions
            recalculate the summary. """
            operator = getattr(self.engine, operation)
            for summ in coll:
                try:
                    operator(summ, **kwargs)
                except ConditionalCheckFailedException:
                    # If somebody else updated a summary, there's probably a
                    # new package that got mutated after we read Dynamo. We
                    # need to rebuild the whole summary.
                    # Redoing it once will suffice in the overwhelming majority
                    # of the cases. If not, it'll have to wait until the next
                    # rebuild.

                    LOG.warn(
                        "Conflict while trying to %s %r. Recalculating.",
                        operation,
                        summ,
                    )

                    pkgs = self.all(summ.name)
                    if not pkgs:
                        do_or_skip('delete', [summ], raise_on_conflict=True)
                        continue

                    summ.refresh(consistent=True)
                    summ = _clear_summary(summ)
                    for pkg in pkgs:
                        summ.update_with(pkg)

                    do_or_skip('sync', [summ], raise_on_conflict=True)

        do_or_skip('save', cache_updates.new_packages, overwrite=False, warn=False)
        # If somebody else updated a package, they're probably operating on
        # fresher data. In those cases, skip the change.
        do_or_skip('sync', updated_packages, raise_on_conflict=True)
        do_or_skip('delete', cache_updates.stale_packages, raise_on_conflict=True)

        do_or_recalc_summaries('save', cache_updates.new_summaries, overwrite=False)
        do_or_recalc_summaries('sync', updated_summaries, raise_on_conflict=True)
        do_or_recalc_summaries('delete', cache_updates.stale_summaries, raise_on_conflict=True)

        LOG.info("Finished persisting cache.")

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

    def clear(self, package):
        summary = self.engine.get(PackageSummary, name=package.name)
        if summary is not None and \
            (summary.unstable == package.version or
             summary.stable == package.version or
             summary.last_modified == package.last_modified):
            _clear_summary(summary)
            all_packages = self.engine.scan(DynamoPackage)\
                .filter(DynamoPackage.filename != package.filename,
                        name=package.name)
            delete_summary = True
            for package in all_packages:
                delete_summary = False
                summary.update_with(package)
            if delete_summary:
                summary.delete()
            else:
                summary.sync()

        self.engine.delete(package)

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
        summary = self.engine.get(PackageSummary, name=package.name)
        if summary is None:
            summary = PackageSummary(package)
        else:
            summary.update_with(package)

        self.engine.save(package)
        self.engine.sync(summary)
