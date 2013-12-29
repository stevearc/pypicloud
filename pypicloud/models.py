""" Model objects """
import os
import time
from datetime import datetime

from boto.s3.key import Key
from pip.util import splitext
from sqlalchemy import Column, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base

from .compat import total_ordering


Base = declarative_base()  # pylint: disable=C0103


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
class Package(Base):

    """
    Representation of a versioned package

    Parameters
    ----------
    name : str
        The name of the package (will be normalized)
    version : str, optional
        The version number of the package
    path : str, optional
        The absolute S3 path of the package file

    """
    __tablename__ = 'packages'
    name = Column(Text(), primary_key=True)
    version = Column(Text(), primary_key=True)
    path = Column(Text(), nullable=False)
    _url = Column('url', Text())
    _expire = Column('expire', DateTime())

    def __init__(self, name, version=None, path=None):
        self.name = name
        self.version = version
        self.path = path
        self._url = None
        self._expire = None

    def get_url(self, request):
        """ Create or return an HTTP url for an S3 path """
        if self._url is None or datetime.now() > self._expire:
            key = Key(request.bucket)
            key.key = self.path
            expire_after = time.time() + request.registry.expire_after
            self._url = key.generate_url(
                expire_after, expires_in_absolute=True)
            self._expire = datetime.fromtimestamp(expire_after -
                                                  request.registry.buffer_time)
        return self._url

    @staticmethod
    def normalize_name(name):
        """ Normalize a python package name """
        return name.lower().replace('-', '_')

    @classmethod
    def from_key(cls, key):
        """ Construct a Package object from the S3 key """
        name = key.get_metadata('name')
        version = key.get_metadata('version')

        # We used to not store metadata. This is for backwards compatibility
        if name is None or version is None:
            filename = os.path.basename(key.key)
            name, version = cls._parse_package_and_version(filename)

        return cls(cls.normalize_name(name), version, key.key)

    @classmethod
    def _parse_package_and_version(cls, path):
        """ Parse the package name and version number from a path """
        filename = splitext(path)[0]
        if filename.endswith('.tar'):
            filename = filename[:-len('.tar')]
        if '-' not in filename:
            return filename, ''
        path_components = filename.split('-')
        for i, comp in enumerate(path_components):
            if comp[0].isdigit():
                return ('_'.join(path_components[:i]).lower(),
                        '-'.join(path_components[i:]))
        return filename.lower().replace('-', '_'), ''

    def __hash__(self):
        return hash(self.name) + hash(self.version)

    def __eq__(self, other):
        return self.name == other.name and self.version == other.version

    def __lt__(self, other):
        return (self.name, self.version) < (other.name, other.version)

    def __str__(self):
        return unicode(self).encode('utf-8')

    def __unicode__(self):
        return u'Package(%s, %s)' % (self.name, self.version)
