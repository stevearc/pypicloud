""" S3-backed pypi server """
import boto.s3
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.config import Configurator
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.security import (Allow, Deny, Authenticated, Everyone,
                              ALL_PERMISSIONS)
from pyramid.settings import asbool
from sqlalchemy import engine_from_config
from sqlalchemy.orm import sessionmaker
# pylint: disable=F0401,E0611
from zope.sqlalchemy import ZopeTransactionExtension
# pylint: enable=F0401,E0611

from .auth import auth_callback, BasicAuthenticationPolicy
from .models import Package


try:
    from ._version import *  # pylint: disable=F0401,W0401
except ImportError:
    __version__ = 'unknown'


class Root(dict):

    """ Root context for PyPI Cloud """
    __name__ = __parent__ = None
    __acl__ = [
        (Allow, Authenticated, ALL_PERMISSIONS),
        (Deny, Everyone, ALL_PERMISSIONS),
    ]


def _bucket(request):
    """ Accessor for S3 bucket """
    return request.registry.s3bucket


def _db(request):
    """ Access a sqlalchemy session """
    maker = request.registry.dbmaker
    session = maker()

    def cleanup(request):
        """ Close the session after the request """
        session.close()
    request.add_finished_callback(cleanup)

    return session


def _packages(request, name=None):
    """ Accessor for Packages """
    if request.db.query(Package).first() is None:
        keys = request.bucket.list(request.registry.prefix)
        packages = []
        for key in keys:
            pkg = Package.from_path(key.name)
            if name is None or pkg.name == name:
                packages.append(pkg)
            request.db.add(pkg)
        return packages
    else:
        query = request.db.query(Package)
        if name is not None:
            query = query.filter_by(name=name)
        return query.all()


NO_ARG = object()


def _param(request, name, default=NO_ARG):
    """
    Access a parameter

    Parameters
    ----------
    request : :class:`~pyramid.request.Request`
    name : str
        The name of the parameter to retrieve
    default : object, optional
        The default value to use if none is found

    Raises
    ------
    exc : :class:`~pyramid.httpexceptions.HTTPBadRequest`
        If a parameter is requested that does not exist and no default was
        provided

    """
    try:
        return request.params[name]
    except (KeyError, ValueError):
        if default is NO_ARG:
            raise HTTPBadRequest('Missing argument %s' % name)
        else:
            return default


def main(config, **settings):
    """ This function returns a Pyramid WSGI application.
    """
    config = Configurator(
        settings=settings,
        root_factory=Root,
        authorization_policy=ACLAuthorizationPolicy(),
        authentication_policy=BasicAuthenticationPolicy(auth_callback),
    )

    s3conn = boto.connect_s3(
        aws_access_key_id=settings.get('aws.access_key'),
        aws_secret_access_key=settings.get('aws.secret_key'))
    config.registry.s3bucket = s3conn.get_bucket(settings['aws.bucket'])

    config.registry.prefix = settings.get('aws.prefix', '')
    config.registry.expire_after = int(settings.get('aws.expire_after',
                                                    60 * 60 * 24))
    config.registry.buffer_time = int(settings.get('aws.buffer_time',
                                                   300))
    config.registry.fallback_url = settings.get('pypi.fallback_url',
                                                'http://pypi.python.org/simple')
    config.registry.use_fallback = asbool(settings.get('pypi.use_fallback',
                                                       True))

    config.add_request_method(_db, name='db', reify=True)
    engine = engine_from_config(settings, prefix='sqlalchemy.')
    config.registry.dbmaker = sessionmaker(bind=engine,
                                           extension=ZopeTransactionExtension())

    config.add_request_method(_bucket, name='bucket', reify=True)
    config.add_request_method(_packages, name='packages')
    config.add_request_method(_param, name='param')

    # Configure routes
    config.add_route('index', '/')
    config.add_route('simple', '/simple{_:/?}')
    config.add_route('packages', '/packages{_:/?}')
    config.add_route('package_versions', '/simple/{package:[^/]+}{_:/?}')

    config.scan()
    return config.make_wsgi_app()
