""" Store package data in a SQL database """
from datetime import datetime

import logging
import transaction
from pkg_resources import parse_version
from sqlalchemy import (engine_from_config, distinct, and_, or_, Column,
                        DateTime, String)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.types import TypeDecorator, TEXT
from sqlalchemy.ext.mutable import Mutable
# pylint: disable=F0401,E0611,W0403
from zope.sqlalchemy import ZopeTransactionExtension
# pylint: enable=F0401,E0611,W0403

from .base import ICache
from pypicloud.models import Package
import json


LOG = logging.getLogger(__name__)

Base = declarative_base()  # pylint: disable=C0103


class JSONEncodedDict(TypeDecorator):  # pylint: disable=W0223

    "Represents an immutable structure as a json-encoded string."

    impl = TEXT

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = json.loads(value)
        return value


class MutableDict(Mutable, dict):

    """ SQLAlchemy dict field that tracks changes """

    @classmethod
    def coerce(cls, key, value):
        "Convert plain dictionaries to MutableDict."

        if not isinstance(value, MutableDict):
            if isinstance(value, dict):
                return MutableDict(value)

            # this call will raise ValueError
            return Mutable.coerce(key, value)
        else:
            return value

    def __setitem__(self, key, value):
        "Detect dictionary set events and emit change events."

        dict.__setitem__(self, key, value)
        self.changed()

    def __delitem__(self, key):
        "Detect dictionary del events and emit change events."

        dict.__delitem__(self, key)
        self.changed()

MutableDict.associate_with(JSONEncodedDict)


class SQLPackage(Package, Base):

    """ Python package stored in SQLAlchemy """
    __tablename__ = 'packages'
    filename = Column(String(255, convert_unicode=True), primary_key=True)
    name = Column(String(255, convert_unicode=True), index=True, nullable=False)
    version = Column(String(1000, convert_unicode=True), nullable=False)
    last_modified = Column(DateTime(), index=True, nullable=False)
    summary = Column(String(255, convert_unicode=True), index=True, nullable=True)
    data = Column(JSONEncodedDict(), nullable=False)


def create_schema(engine):
    """
    Create the database schema if needed

    Parameters
    ----------
    engine : :class:`sqlalchemy.Engine`

    Notes
    -----
    The method should only be called after importing all modules containing
    models which extend the ``Base`` object.

    """
    Base.metadata.create_all(bind=engine)


def drop_schema(engine):
    """
    Drop the database schema

    Parameters
    ----------
    engine : :class:`sqlalchemy.Engine`

    Notes
    -----
    The method should only be called after importing all modules containing
    models which extend the ``Base`` object.

    """
    Base.metadata.drop_all(bind=engine)


class SQLCache(ICache):

    """ Caching database that uses SQLAlchemy """
    package_class = SQLPackage

    def __init__(self, request=None, dbmaker=None, **kwargs):
        super(SQLCache, self).__init__(request, **kwargs)
        self.dbmaker = dbmaker
        self.db = self.dbmaker()

        if request is not None:
            def cleanup(_):
                """ Close the session after the request """
                self.db.close()
            request.add_finished_callback(cleanup)

    def reload_if_empty(self):
        super(SQLCache, self).reload_if_empty()
        if self.request is None:
            transaction.commit()
            self.db.close()

    def reload_if_needed(self):
        super(SQLCache, self).reload_if_needed()
        if self.request is None:
            transaction.commit()
            self.db.close()

    @classmethod
    def configure(cls, settings):
        kwargs = super(SQLCache, cls).configure(settings)
        engine = engine_from_config(settings, prefix='db.')
        # Create SQL schema if not exists
        create_schema(engine)
        kwargs['dbmaker'] = sessionmaker(bind=engine,
                                         extension=ZopeTransactionExtension())
        return kwargs

    def fetch(self, filename):
        self.reload_if_needed()
        return self.db.query(SQLPackage).filter_by(filename=filename).first()

    def all(self, name):
        self.reload_if_needed()
        pkgs = self.db.query(SQLPackage).filter_by(name=name).all()
        pkgs.sort(reverse=True)
        return pkgs

    def distinct(self):
        self.reload_if_needed()
        names = self.db.query(distinct(SQLPackage.name))\
            .order_by(SQLPackage.name).all()
        return [n[0] for n in names]

    def search(self, criteria, query_type):
        """
        Perform a search.

        Queries are performed as follows:

            For the AND query_type, queries within a column will utilize the
            AND operator, but will not conflict with queries in another column.

                (column1 LIKE '%a%' AND column1 LIKE '%b%')
                OR
                (column2 LIKE '%c%' AND column2 LIKE '%d%')

            For the OR query_type, all queries will utilize the OR operator:

                (column1 LIKE '%a%' OR column1 LIKE '%b%')
                OR
                (column2 LIKE '%c%' OR column2 LIKE '%d%')

        """
        self.reload_if_needed()
        conditions = []
        for key, queries in criteria.items():
            # Make sure search key exists in the package class.
            # It should be either "name" or "summary".
            field = getattr(self.package_class, key, None)
            if not field:
                continue

            column_conditions = []

            for query in queries:
                # Generate condition and add to list
                condition = field.like('%' + query + '%')
                column_conditions.append(condition)

            # Check if conditions for this column were generated
            if column_conditions:
                if query_type == 'and':
                    operator = and_
                else:
                    operator = or_
                conditions.append(operator(*column_conditions))

        # Piece together the queries. Refer to the method docstring for
        # examples as to how this works.
        results = self.db.query(SQLPackage).filter(or_(*conditions))

        # Extract only the most recent version for each package
        latest_map = {}
        for package in results.all():
            if package.name not in latest_map or \
               package > latest_map[package.name]:
                latest_map[package.name] = package

        return latest_map.values()

    def summary(self):
        self.reload_if_needed()
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
        # Release any transactions before we go reloading schema
        transaction.abort()
        engine = self.dbmaker.kw['bind']
        drop_schema(engine)
        create_schema(engine)

    def save(self, package):
        self.db.merge(package)
