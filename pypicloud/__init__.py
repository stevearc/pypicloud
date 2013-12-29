""" S3-backed pypi server """
from functools import partial
import boto.s3
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.config import Configurator
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.settings import asbool
from sqlalchemy import engine_from_config
from sqlalchemy.orm import sessionmaker
# pylint: disable=F0401,E0611
from zope.sqlalchemy import ZopeTransactionExtension
# pylint: enable=F0401,E0611

from .auth import auth_callback, BasicAuthenticationPolicy
from .models import Package
from .route import Root, subpath


try:
    from ._version import *  # pylint: disable=F0401,W0401
except ImportError:
    __version__ = 'unknown'


class CustomPredicateConfig(Configurator):

    """
    Custom Configurator that allows you to add default custom predicates

    Parameters
    ----------
    custom_predicates : tuple
        The predicates that will be applied to every view by default

    """

    def __init__(self, *args, **kwargs):
        custom_predicates = kwargs.pop('custom_predicates', None)
        if custom_predicates is not None:
            # We have to set them on the class becase Configurator replicates
            # itself and we have to keep the args
            self.__class__.custom_predicates = custom_predicates
        super(CustomPredicateConfig, self).__init__(*args, **kwargs)

        # Patch the add_view method to add a default argument
        if self.custom_predicates is not None:
            self.add_view = partial(self.add_view,
                                    custom_predicates=self.custom_predicates)


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


def _fetch_if_needed(request):
    """ Make sure local database is populated with packages """
    if request.db.query(Package).first() is None:
        keys = request.bucket.list(request.registry.prefix)
        for key in keys:
            pkg = Package.from_key(key)
            request.db.add(pkg)


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
    realm = settings.get('pypi.realm', 'pypicloud')
    config = CustomPredicateConfig(
        settings=settings,
        root_factory=Root,
        authorization_policy=ACLAuthorizationPolicy(),
        authentication_policy=BasicAuthenticationPolicy(auth_callback, realm),
        custom_predicates=(subpath(),),
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
    config.add_request_method(
        _fetch_if_needed, name='fetch_packages_if_needed')
    config.add_request_method(_param, name='param')

    config.registry.prepend_hash = asbool(settings.get('pypi.prepend_hash',
                                                       False))

    config.add_route('root', '/')

    config.scan()
    return config.make_wsgi_app()
