""" Model objects """
import re
from datetime import datetime

import logging
import pkg_resources
from sqlalchemy import Column, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base

from .compat import total_ordering


LOG = logging.getLogger(__name__)

Base = declarative_base()  # pylint: disable=C0103


def normalize_name(name):
    """ Normalize a python package name """
    return name.lower().replace('-', '_')


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


@total_ordering
class Package(object):

    """
    Representation of a versioned package

    Parameters
    ----------
    name : str
        The name of the package (will be normalized)
    version : str
        The version number of the package
    path : str
        The absolute S3 path of the package file
    last_modified : datetime
        The datetime when this package was uploaded
    url : str, optional
        The generated S3 url (may be out of date; access this from
        :meth:`~.get_url`)
    expire : :class:`~datetime.datetime`, optional
        When the generated S3 url expires

    """

    def __init__(self, name, version, path, last_modified, url=None,
                 expire=None):
        self.name = normalize_name(name)
        self.version = version
        self.path = path
        self.last_modified = last_modified
        self.url = url
        if expire is not None and not isinstance(expire, datetime):
            self.expire = datetime.fromtimestamp(float(expire))
        else:
            self.expire = expire

    @property
    def filename(self):
        """ Getter for raw filename with no prefixes """
        filename = self.path.split('/')[-1]
        return filename

    def get_url(self, request):
        """ Create path to the download link """
        return request.db.get_url(self)

    @property
    def is_prerelease(self):
        """ Returns True if the version is a prerelease version """
        return re.match(r'^\d+(\.\d+)*$', self.version) is None

    def __hash__(self):
        return hash(self.name) + hash(self.version)

    def __eq__(self, other):
        return self.name == other.name and self.version == other.version

    def __lt__(self, other):
        return ((self.name, pkg_resources.parse_version(self.version)) <
                (other.name, pkg_resources.parse_version(other.version)))

    def __repr__(self):
        return unicode(self)

    def __str__(self):
        return unicode(self).encode('utf-8')

    def __unicode__(self):
        return u'Package(%s, %s)' % (self.name, self.version)

    def __json__(self, request):
        return {
            'name': self.name,
            'last_modified': self.last_modified,
            'version': self.version,
            'url': self.get_url(request),
        }


class SQLPackage(Package, Base):

    """ Python package stored in SQLAlchemy """
    __tablename__ = 'packages'
    name = Column(Text(), primary_key=True)
    version = Column(Text(), primary_key=True)
    last_modified = Column(DateTime(), index=True, nullable=False)
    path = Column(Text(), nullable=False)
    url = Column('url', Text())
    expire = Column('expire', DateTime())
