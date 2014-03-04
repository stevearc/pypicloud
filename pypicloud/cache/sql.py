""" Store package data in a SQL database """
from datetime import datetime

import logging
import transaction
from pkg_resources import parse_version
from sqlalchemy import engine_from_config, distinct, Column, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
# pylint: disable=F0401,E0611
from zope.sqlalchemy import ZopeTransactionExtension
# pylint: enable=F0401,E0611

from .base import ICache
from pypicloud.models import Package


LOG = logging.getLogger(__name__)

Base = declarative_base()  # pylint: disable=C0103


class SQLPackage(Package, Base):

    """ Python package stored in SQLAlchemy """
    __tablename__ = 'packages'
    name = Column(Text(), primary_key=True)
    version = Column(Text(), primary_key=True)
    last_modified = Column(DateTime(), index=True, nullable=False)
    path = Column(Text(), nullable=False)
    url = Column('url', Text())
    expire = Column('expire', DateTime())


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
    dbtype = 'sql'
    autocommit = False
    package_class = SQLPackage
    dbmaker = None

    def __init__(self, request=None):
        super(SQLCache, self).__init__(request)
        self.db = self.dbmaker()

        if request is not None:
            def cleanup(_):
                """ Close the session after the request """
                self.db.close()
            request.add_finished_callback(cleanup)

    @classmethod
    def reload_if_needed(cls):
        cache = super(SQLCache, cls).reload_if_needed()
        transaction.commit()
        cache.db.close()

    @classmethod
    def configure(cls, config):
        super(SQLCache, cls).configure(config)
        settings = config.get_settings()
        engine = engine_from_config(settings, prefix='db.')
        cls.dbmaker = sessionmaker(
            bind=engine, extension=ZopeTransactionExtension())
        # Create SQL schema if not exists
        create_schema(engine)

    def _fetch(self, name, version):
        return self.db.query(SQLPackage).filter_by(name=name,
                                                   version=version).first()

    def _all(self, name):
        pkgs = self.db.query(SQLPackage).filter_by(name=name).all()
        pkgs.sort(reverse=True)
        return pkgs

    def distinct(self):
        names = self.db.query(distinct(SQLPackage.name))\
            .order_by(SQLPackage.name).all()
        return [n[0] for n in names]

    def summary(self):
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
        engine = self.dbmaker.kw['bind']
        drop_schema(engine)
        create_schema(engine)

    def save(self, package):
        self.db.add(package)
