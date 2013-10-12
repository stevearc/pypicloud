""" Model objects """
import os
import time
from datetime import datetime

from boto.s3.key import Key
from sqlalchemy import Column, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base


Base = declarative_base()  # pylint: disable=C0103


def create_schema(registry):
    """
    Create the database schema if needed

    Parameters
    ----------
    registry : dict
        The configuration registry

    Notes
    -----
    The method should only be called after importing all modules containing
    models which extend the ``Base`` object.

    """
    Base.metadata.create_all(bind=registry.dbmaker.kw['bind'])


def drop_schema(registry):
    """
    Drop the database schema

    Parameters
    ----------
    registry : dict
        The configuration registry

    Notes
    -----
    The method should only be called after importing all modules containing
    models which extend the ``Base`` object.

    """
    Base.metadata.drop_all(bind=registry.dbmaker.kw['bind'])


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
        self.name = name.lower().replace('-', '_')
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

    @property
    def filename(self):
        """ Just the package file name with no leading path """
        return os.path.basename(self.path)

    @classmethod
    def from_path(cls, path):
        """ Construct a Package object from the S3 path """
        filename = os.path.basename(path)
        name, version = cls.parse_package_and_version(filename)
        return cls(name, version, path=path)

    @classmethod
    def parse_package_and_version(cls, path):
        """ Parse the package name and version number from a path """
        filename, _ = os.path.splitext(path)
        if filename.endswith('.tar'):
            filename = filename[:-len('.tar')]
        if '-' not in filename:
            return filename, ''
        path_components = filename.split('-')
        for i, comp in enumerate(path_components):
            if comp[0].isdigit():
                return ('-'.join(path_components[:i]),
                        '-'.join(path_components[i:]))
        return filename, ''

    def __hash__(self):
        return hash(self.name, self.version)

    def __eq__(self, other):
        return self.name == other.name and self.version == other.version

    def __str__(self):
        return unicode(self).encode('utf-8')

    def __unicode__(self):
        return u'Package(%s, %s)' % (self.name, self.version)
