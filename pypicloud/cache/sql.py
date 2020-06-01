""" Store package data in a SQL database """
import json
import logging
from datetime import datetime

import zope.sqlalchemy
from pyramid.settings import asbool
from sqlalchemy import Column, DateTime, String, and_, distinct, engine_from_config, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.mutable import Mutable
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func
from sqlalchemy.types import TEXT, TypeDecorator

from pypicloud.models import Package

from .base import ICache

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

    __tablename__ = "packages"
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

    def __init__(self, request=None, dbmaker=None, graceful_reload=False, **kwargs):
        super(SQLCache, self).__init__(request, **kwargs)
        self.dbmaker = dbmaker
        self.db = self.dbmaker()
        self.graceful_reload = graceful_reload

        if request is not None:
            zope.sqlalchemy.register(self.db, transaction_manager=request.tm)

    def new_package(self, *args, **kwargs):
        return SQLPackage(*args, **kwargs)

    def reload_if_needed(self):
        super(SQLCache, self).reload_if_needed()
        if self.request is None:
            self.db.commit()
            self.db.close()

    @classmethod
    def configure(cls, settings):
        kwargs = super(SQLCache, cls).configure(settings)
        graceful_reload = asbool(settings.pop("db.graceful_reload", False))
        engine = engine_from_config(settings, prefix="db.")
        # Create SQL schema if not exists
        create_schema(engine)
        kwargs["dbmaker"] = sessionmaker(bind=engine)
        kwargs["graceful_reload"] = graceful_reload
        return kwargs

    @classmethod
    def postfork(cls, **kwargs):
        # Have to dispose of connections after uWSGI forks,
        # otherwise they'll get corrupted.
        kwargs["dbmaker"].kw["bind"].dispose()

    def fetch(self, filename):
        return self.db.query(SQLPackage).filter_by(filename=filename).first()

    def all(self, name):
        pkgs = self.db.query(SQLPackage).filter_by(name=name).all()
        pkgs.sort(reverse=True)
        return pkgs

    def distinct(self):
        names = self.db.query(distinct(SQLPackage.name)).order_by(SQLPackage.name).all()
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
        conditions = []
        for key, queries in criteria.items():
            # Make sure search key exists in the package class.
            # It should be either "name" or "summary".
            field = getattr(SQLPackage, key, None)
            if not field:
                continue

            column_conditions = []

            for query in queries:
                # Generate condition and add to list
                condition = field.like("%" + query + "%")
                column_conditions.append(condition)

            # Check if conditions for this column were generated
            if column_conditions:
                if query_type == "and":
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
            if package.name not in latest_map or package > latest_map[package.name]:
                latest_map[package.name] = package

        return latest_map.values()

    def summary(self):
        subquery = (
            self.db.query(
                SQLPackage.name,
                func.max(SQLPackage.last_modified).label("last_modified"),
            )
            .group_by(SQLPackage.name)
            .subquery()
        )
        rows = self.db.query(
            SQLPackage.name, SQLPackage.last_modified, SQLPackage.summary
        ).filter(
            (SQLPackage.name == subquery.c.name)
            & (SQLPackage.last_modified == subquery.c.last_modified)
        )

        # Dedupe because two packages may share the same last_modified
        seen_packages = set()
        packages = []
        for row in rows:
            if row[0] in seen_packages:
                continue
            seen_packages.add(row[0])
            packages.append(
                {"name": row[0], "last_modified": row[1], "summary": row[2]}
            )
        return packages

    def clear(self, package):
        self.db.delete(package)

    def clear_all(self):
        # Release any transactions before we go reloading schema
        if self.request is None:
            self.db.rollback()
        else:
            self.request.tm.abort()
        engine = self.dbmaker.kw["bind"]
        drop_schema(engine)
        create_schema(engine)

    def save(self, package):
        self.db.merge(package)

    def reload_from_storage(self, clear=True):
        if not self.graceful_reload:
            return super(SQLCache, self).reload_from_storage(clear)

        LOG.info("Rebuilding cache from storage")
        # Log start time
        start = datetime.utcnow()
        # Fetch packages from storage s1
        s1 = set(self.storage.list(SQLPackage))
        # Fetch cache packages c1
        c1 = set(self.db.query(SQLPackage).all())
        # Add missing packages to cache (s1 - c1)
        missing = s1 - c1
        if missing:
            LOG.info("Adding %d missing packages to cache", len(missing))
            for pkg in missing:
                self.db.merge(pkg)
        # Delete extra packages from cache (c1 - s1) when last_modified < start
        # The time filter helps us avoid deleting packages that were
        # concurrently uploaded.
        extra1 = [p for p in (c1 - s1) if p.last_modified <= start]
        if extra1:
            LOG.info("Removing %d extra packages from cache", len(extra1))
            for pkg in extra1:
                self.db.query(SQLPackage).filter(
                    SQLPackage.filename == pkg.filename
                ).delete(synchronize_session=False)

        # If any packages were concurrently deleted during the cache rebuild,
        # we can detect them by polling storage again and looking for any
        # packages that were present in s1 and are missing from s2
        s2 = set(self.storage.list(SQLPackage))
        # Delete extra packages from cache (s1 - s2)
        extra2 = s1 - s2
        if extra2:
            LOG.info(
                "Removing %d packages from cache that were concurrently "
                "deleted during rebuild",
                len(extra2),
            )
            for pkg in extra2:
                self.db.query(SQLPackage).filter(
                    SQLPackage.filename == pkg.filename
                ).delete(synchronize_session=False)

    def check_health(self):
        try:
            self.db.query(SQLPackage).first()
        except SQLAlchemyError as e:
            return (False, str(e))
        else:
            return (True, "")
