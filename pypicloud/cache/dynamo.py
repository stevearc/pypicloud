""" Store package data in DynamoDB """
from datetime import datetime

import time
import logging
from dynamo3 import DynamoDBConnection
from pkg_resources import parse_version
from pyramid.settings import asbool
import itertools

from .base import ICache
from pypicloud.models import Package


try:
    from flywheel import (Engine, Model, Field, GlobalIndex, CheckFailed,
                          __version__)
    from flywheel.fields.types import UTC
    if parse_version(__version__) < parse_version('0.2.0'):  # pragma: no cover
        raise ValueError("Pypicloud requires flywheel>=0.2.0")
except ImportError:  # pragma: no cover
    raise ImportError("You must 'pip install flywheel' before using "
                      "DynamoDB as the cache database")

LOG = logging.getLogger(__name__)


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
        self.last_modified = package.last_modified.replace(tzinfo=UTC)

    def update_with(self, package):
        """ Update summary with a package """
        if self.name != package.name:
            LOG.error("Summary name '%s' doesn't match package name '%s'",
                      self.name, package.name)
            return
        self.unstable = max(self.unstable, package.version, key=parse_version)
        self.last_modified = max(self.last_modified.replace(tzinfo=UTC),
                                 package.last_modified.replace(tzinfo=UTC))
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
        pkgs = {}
        for pkg in self.engine.scan(DynamoPackage):
            pkgs[pkg.filename] = pkg

        # Group packages by name
        to_save = {}
        for pkg in self.storage.list(self.package_class):
            if pkg.filename in pkgs:
                # If the package is already in the cache, ignore it.
                del pkgs[pkg.filename]
            else:
                packages = to_save.setdefault(pkg.name, [])
                packages.append(pkg)

        # Recalculate the summary objects from the packages from storage
        summaries = []
        for packages in to_save.itervalues():
            summary = PackageSummary(packages[0])
            for package in packages:
                summary.update_with(package)
            summaries.append(summary)
        # Save all the packages and summaries in a big batch
        self.engine.save(itertools.chain(*to_save.itervalues()),
                         overwrite=True)
        self.engine.save(summaries, overwrite=True)

        # Batch delete all stale packages & summaries not in storage
        delete_summaries = set()
        for package in pkgs.itervalues():
            if package.name not in to_save:
                delete_summaries.add(package.name)
        self.engine.delete_key(DynamoPackage, pkgs.iterkeys())
        self.engine.delete_key(PackageSummary, delete_summaries)

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
            summary.stable = None
            summary.unstable = '0'
            summary.last_modified = datetime.fromtimestamp(0) \
                .replace(tzinfo=UTC)
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
        max_attempts = 5
        saved_package = False
        for attempt in range(max_attempts):
            summary = self.engine.get(PackageSummary, name=package.name)
            if summary is None:
                summary = PackageSummary(package)
            else:
                summary.update_with(package)

            if not saved_package:
                self.engine.save(package, overwrite=True)
                saved_package = True
            try:
                self.engine.sync(summary)
            except CheckFailed:
                LOG.warning("Concurrent updates of %s summary", package.name)
                time.sleep(2**attempt - 1)
            else:
                return
        raise RuntimeError("Failed to cache package %s" % package.filename)
