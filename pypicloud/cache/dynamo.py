""" Store package data in DynamoDB """
from datetime import datetime

import logging
from dynamo3 import DynamoDBConnection
from pkg_resources import parse_version
from pyramid.settings import asbool

from .base import ICache
from pypicloud.models import Package
from pypicloud.util import get_settings


try:
    from flywheel import Engine, Model, Field, GlobalIndex, __version__
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
    summary = Field()
    data = Field(data_type=dict)


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
    package_class = DynamoPackage

    def __init__(self, request=None, engine=None, **kwargs):
        super(DynamoCache, self).__init__(request, **kwargs)
        self.engine = engine

    @classmethod
    def configure(cls, settings):
        kwargs = super(DynamoCache, cls).configure(settings)

        access_key = settings.get('db.aws_access_key_id')
        secret_key = settings.get('db.aws_secret_access_key')
        region = settings.get('db.region')
        host = settings.get('db.host')
        port = int(settings.get('db.port', 8000))
        secure = asbool(settings.get('db.secure', False))
        namespace = settings.get('db.namespace', ())

        if host is not None:
            connection = DynamoDBConnection.connect(region,
                                                    host=host,
                                                    port=port,
                                                    is_secure=secure,
                                                    access_key=access_key,
                                                    secret_key=secret_key)
        elif region is not None:
            connection = DynamoDBConnection.connect(region,
                                                    access_key=access_key,
                                                    secret_key=secret_key)
        else:
            raise ValueError("Must specify either db.region or db.host!")
        kwargs['engine'] = engine = Engine(namespace=namespace,
                                           dynamo=connection)

        engine.register(DynamoPackage, PackageSummary)
        engine.create_schema()
        return kwargs

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
        self.engine.delete(package)
        remaining = self.engine(DynamoPackage) \
            .filter(DynamoPackage.name == package.name) \
            .scan_limit(1) \
            .count()
        if remaining == 0:
            self.engine.delete_key(PackageSummary, name=package.name)

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
        summary = PackageSummary(package)
        self.engine.save([package, summary], overwrite=True)
