""" Store package data in DynamoDB """
import logging
from collections import defaultdict
from datetime import datetime

from dynamo3 import DynamoDBConnection
from pkg_resources import parse_version
from pyramid.settings import asbool, aslist

from pypicloud.models import Package

from .base import ICache

try:
    from flywheel import Engine, Model, Field, GlobalIndex, __version__
    from flywheel.fields.types import UTC

    if parse_version(__version__) < parse_version("0.2.0"):  # pragma: no cover
        raise ValueError("Pypicloud requires flywheel>=0.2.0")
except ImportError:  # pragma: no cover
    raise ImportError(
        "You must 'pip install flywheel' before using " "DynamoDB as the cache database"
    )

LOG = logging.getLogger(__name__)


class DynamoPackage(Package, Model):

    """ Python package stored in DynamoDB """

    __metadata__ = {"global_indexes": [GlobalIndex("name-index", "name")]}
    filename = Field(hash_key=True)
    name = Field()
    version = Field()
    last_modified = Field(data_type=datetime)
    summary = Field()
    data = Field(data_type=dict)

    def __init__(self, *args, **kwargs):
        super(DynamoPackage, self).__init__(*args, **kwargs)
        # DynamoDB doesn't play nice with empty strings.
        if not self.summary:
            self.summary = None


class PackageSummary(Model):

    """ Aggregate data about packages """

    name = Field(hash_key=True)
    summary = Field()
    last_modified = Field(data_type=datetime)

    def __init__(self, package):
        super(PackageSummary, self).__init__(package.name)
        self.last_modified = package.last_modified.replace(tzinfo=UTC)
        self.summary = package.summary


class DynamoCache(ICache):

    """ Caching database that uses DynamoDB """

    def __init__(self, request=None, engine=None, graceful_reload=False, **kwargs):
        super(DynamoCache, self).__init__(request, **kwargs)
        self.engine = engine
        self.graceful_reload = graceful_reload

    def new_package(self, *args, **kwargs):
        return DynamoPackage(*args, **kwargs)

    @classmethod
    def configure(cls, settings):
        kwargs = super(DynamoCache, cls).configure(settings)

        access_key = settings.get("db.aws_access_key_id")
        secret_key = settings.get("db.aws_secret_access_key")
        region = settings.get("db.region_name")
        host = settings.get("db.host")
        port = int(settings.get("db.port", 8000))
        secure = asbool(settings.get("db.secure", False))
        namespace = settings.get("db.namespace", ())
        graceful_reload = asbool(settings.get("db.graceful_reload", False))

        tablenames = aslist(settings.get("db.tablenames", []))
        if tablenames:
            if len(tablenames) != 2:
                raise ValueError("db.tablenames must be a 2-element list")
            DynamoPackage.meta_.name = tablenames[0]
            PackageSummary.meta_.name = tablenames[1]

        if host is not None:
            connection = DynamoDBConnection.connect(
                region,
                host=host,
                port=port,
                is_secure=secure,
                access_key=access_key,
                secret_key=secret_key,
            )
        elif region is not None:
            connection = DynamoDBConnection.connect(
                region, access_key=access_key, secret_key=secret_key
            )
        else:
            raise ValueError("Must specify either db.region_name or db.host!")
        kwargs["engine"] = engine = Engine(namespace=namespace, dynamo=connection)
        kwargs["graceful_reload"] = graceful_reload

        engine.register(DynamoPackage, PackageSummary)
        LOG.info("Checking if DynamoDB tables exist")
        engine.create_schema()
        return kwargs

    def fetch(self, filename):
        return self.engine.get(DynamoPackage, filename=filename)

    def all(self, name):
        return sorted(self.engine.query(DynamoPackage).filter(name=name), reverse=True)

    def distinct(self):
        names = set()
        for summary in self.engine.scan(PackageSummary):
            names.add(summary.name)
        return sorted(names)

    def summary(self):
        summaries = sorted(self.engine.scan(PackageSummary), key=lambda s: s.name)
        return [s.__json__() for s in summaries]

    def clear(self, package):
        self.engine.delete(package)
        self._maybe_delete_summary(package.name)

    def _maybe_delete_summary(self, package_name):
        """ Check for any package with the name. Delete summary if 0 """
        remaining = (
            self.engine(DynamoPackage)
            .filter(DynamoPackage.name == package_name)
            .scan_limit(1)
            .count()
        )
        if remaining == 0:
            LOG.info("Removing package summary %s", package_name)
            self.engine.delete_key(PackageSummary, name=package_name)

    def clear_all(self):
        # We're replacing the schema, so make sure we save and restore the
        # current table/index throughput
        throughput = {}
        for model in (DynamoPackage, PackageSummary):
            tablename = model.meta_.ddb_tablename(self.engine.namespace)
            desc = self.engine.dynamo.describe_table(tablename)
            tablename = model.meta_.ddb_tablename()
            throughput[tablename] = {
                "read": desc.throughput.read,
                "write": desc.throughput.write,
            }
            for index in desc.global_indexes:
                throughput[tablename][index.name] = {
                    "read": index.throughput.read,
                    "write": index.throughput.write,
                }

        self.engine.delete_schema()
        self.engine.create_schema(throughput=throughput)

    def save(self, package):
        summary = PackageSummary(package)
        self.engine.save([package, summary], overwrite=True)

    def reload_from_storage(self, clear=True):
        if not self.graceful_reload:
            return super(DynamoCache, self).reload_from_storage(clear)
        LOG.info("Rebuilding cache from storage")
        # Log start time
        start = datetime.utcnow().replace(tzinfo=UTC)
        # Fetch packages from storage s1
        s1 = set(self.storage.list(self.new_package))
        # Fetch cache packages c1
        c1 = set(self.engine.scan(DynamoPackage))
        # Add missing packages to cache (s1 - c1)
        missing = s1 - c1
        if missing:
            LOG.info("Adding %d missing packages to cache", len(missing))
            self.engine.save(missing)
        # Delete extra packages from cache (c1 - s1) when last_modified < start
        # The time filter helps us avoid deleting packages that were
        # concurrently uploaded.
        extra1 = [p for p in (c1 - s1) if p.last_modified < start]
        if extra1:
            LOG.info("Removing %d extra packages from cache", len(extra1))
            self.engine.delete(extra1)

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
            self.engine.delete(extra2)
            # Remove these concurrently-deleted files from the list of packages
            # that were missing from the cache. Don't want to use those to
            # update the summaries below.
            missing -= extra2

        # Update the PackageSummary for added packages
        packages_by_name = defaultdict(list)
        for package in missing:
            # Set the tz here so we can compare against the PackageSummary
            package.last_modified = package.last_modified.replace(tzinfo=UTC)
            packages_by_name[package.name].append(package)
        summaries = self.engine.get(PackageSummary, packages_by_name.keys())
        summaries_by_name = {}
        for summary in summaries:
            summaries_by_name[summary.name] = summary
        for name, packages in packages_by_name.items():
            if name in summaries_by_name:
                summary = summaries_by_name[name]
            else:
                summary = PackageSummary(packages[0])
                summaries.append(summary)
            for package in packages:
                if package.last_modified > summary.last_modified:
                    summary.last_modified = package.last_modified
                    summary.summary = package.summary
        if summaries:
            LOG.info("Updating %d package summaries", len(summaries))
            self.engine.save(summaries, overwrite=True)

        # Remove the PackageSummary for deleted packages
        removed = set()
        for package in extra1:
            removed.add(package.name)
        for package in extra2:
            removed.add(package.name)
        for name in removed:
            self._maybe_delete_summary(name)

    def check_health(self):
        try:
            self.engine.scan(PackageSummary).first()
        except Exception as e:
            return False, str(e)
        else:
            return True, ""
