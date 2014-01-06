""" Model objects """
import re
import os
import time
from datetime import datetime

from boto.s3.key import Key
from pip.util import splitext
from sqlalchemy import distinct, Column, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base

from .compat import total_ordering


Base = declarative_base()  # pylint: disable=C0103
PREFIX = re.compile(r'^[A-Fa-f0-9]{4}:')


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
    redis_prefix = 'pypicloud:'

    def __init__(self, name, version, path, _url=None, _expire=None):
        self.name = name
        self.version = version
        self.path = path
        self._url = _url
        if isinstance(_expire, basestring):
            self._expire = datetime.fromtimestamp(float(_expire))
        else:
            self._expire = _expire

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
            if request.dbtype == 'redis':
                self.save(request)
        return self._url

    def filename(self, request):
        """ Getter for raw filename with no prefixes """
        filename = self.path[len(request.registry.prefix):]
        if PREFIX.match(filename):
            return filename[5:]
        else:
            return filename

    @property
    def redis_key(self):
        """ Get a unique key for redis """
        return self._redis_key(self.name, self.version)

    @classmethod
    def _redis_key(cls, name, version):
        """ Get the key to a redis hash that stores a package """
        return "%s%s==%s" % (cls.redis_prefix, name, version)

    @classmethod
    def redis_set(cls):
        """ Get the key to the redis set of package names """
        return cls.redis_prefix + 'set'

    @classmethod
    def redis_version_set(cls, name):
        """ Get the key to a redis set of versions for a package """
        return "%sset:%s" % (cls.redis_prefix, name)

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

    @classmethod
    def reload_from_s3(cls, request):
        """ Make sure local database is populated with packages """
        keys = request.bucket.list(request.registry.prefix)
        cls._load(request, keys)

    @classmethod
    def _load(cls, request, keys):
        """ Load all packages from S3 keys and save to DB """
        if request.dbtype == 'sql':
            for key in keys:
                pkg = Package.from_key(key)
                pkg.save(request)
        elif request.dbtype == 'redis':
            pipe = request.db.pipeline()
            for key in keys:
                pkg = Package.from_key(key)
                pkg.save(request, pipe=pipe)
            pipe.execute()

    @classmethod
    def fetch(cls, request, name, version):
        """ Get matching package if it exists """
        if request.dbtype == 'sql':
            return request.db.query(cls).filter_by(name=name,
                                                   version=version).first()
        elif request.dbtype == 'redis':
            data = request.db.hgetall(cls._redis_key(name, version))
            if not data:
                return None
            pkg = cls(**data)
            return pkg

    @classmethod
    def all(cls, request, name=None):
        """ Search for either all packages or all versions of a package """
        if request.dbtype == 'sql':
            if name is None:
                return request.db.query(Package).order_by(Package.name,
                                                          Package.version).all()
            else:
                return request.db.query(Package).filter_by(name=name)\
                    .order_by(Package.version).all()
        elif request.dbtype == 'redis':
            pipe = request.db.pipeline()
            if name is None:
                for name in request.db.smembers(cls.redis_set()):
                    versions = request.db.smembers(cls.redis_version_set(name))
                    for version in versions:
                        pipe.hgetall(cls._redis_key(name, version))
            else:
                versions = request.db.smembers(cls.redis_version_set(name))
                for version in versions:
                    pipe.hgetall(cls._redis_key(name, version))
            return [cls(**data) for data in pipe.execute()]

    @classmethod
    def distinct(cls, request):
        """ Get all distinct package names """
        if request.dbtype == 'sql':
            names = request.db.query(distinct(Package.name))\
                .order_by(Package.name).all()
            return [n[0] for n in names]
        elif request.dbtype == 'redis':
            return list(request.db.smembers(cls.redis_set()))

    def delete(self, request):
        """ Delete this package from the database """
        if request.dbtype == 'sql':
            request.db.delete(self)
        elif request.dbtype == 'redis':
            del request.db[self.redis_key]
            request.db.srem(self.redis_version_set(self.name), self.version)
            if request.db.scard(self.redis_version_set(self.name)) == 0:
                request.db.srem(self.redis_set(), self.name)

    def save(self, request, pipe=None):
        """ Save this package to the database """
        if request.dbtype == 'sql':
            request.db.add(self)
        elif request.dbtype == 'redis':
            if pipe is None:
                pipe = request.db
            data = {
                'name': self.name,
                'version': self.version,
                'path': self.path,
            }
            if self._url is not None:
                data['_url'] = self._url
            if self._expire is not None:
                data['_expire'] = self._expire.strftime('%s.%f')
            pipe.hmset(self.redis_key, data)
            pipe.sadd(self.redis_set(), self.name)
            pipe.sadd(self.redis_version_set(self.name), self.version)

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

    def __json__(self, request):
        return {
            'name': self.name,
            'version': self.version,
            'url': self.get_url(request),
        }
