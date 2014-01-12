""" S3-backed pypi server """
from pyramid.config import Configurator
from pyramid.renderers import render
from pyramid.settings import asbool, aslist
from pyramid_beaker import session_factory_from_settings
from sqlalchemy import engine_from_config
from sqlalchemy.orm import sessionmaker
# pylint: disable=F0401,E0611
from zope.sqlalchemy import ZopeTransactionExtension
# pylint: enable=F0401,E0611

import boto
from .models import create_schema, Package
from .route import Root


try:
    from ._version import *  # pylint: disable=F0401,W0401
except ImportError:  # pragma: no cover
    __version__ = 'unknown'


def to_json(value):
    """ A json filter for jinja2 """
    return render('json', value)


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


def _redis_db(request):
    """ Access the redis client """
    return request.registry.redis


def _app_url(request, *paths):
    """ Get the base url for the root of the app plus an optional path """
    path = '/'.join(paths)
    if not path.startswith('/'):
        path = '/' + path
    return request.application_url + path


def includeme(config):
    """ Set up and configure the pypicloud app """
    config.set_root_factory(Root)
    config.include('pyramid_tm')
    config.include('pyramid_beaker')
    config.include('pyramid_duh')
    config.include('pyramid_duh.auth')
    config.include('pypicloud.auth')
    config.include('pypicloud.access')
    settings = config.get_settings()

    # Jinja2 configuration
    settings['jinja2.filters'] = {
        'static_url': 'pyramid_jinja2.filters:static_url_filter',
        'tojson': to_json,
    }
    settings['jinja2.directories'] = ['pypicloud:templates']
    config.include('pyramid_jinja2')

    # BEAKER CONFIGURATION
    settings.setdefault('session.type', 'cookie')
    settings.setdefault('session.httponly', 'true')
    config.set_session_factory(session_factory_from_settings(settings))

    s3conn = boto.connect_s3(
        aws_access_key_id=settings.get('aws.access_key'),
        aws_secret_access_key=settings.get('aws.secret_key'))
    config.registry.s3bucket = s3conn.get_bucket(settings['aws.bucket'],
                                                 validate=False)

    config.registry.prefix = settings.get('aws.prefix', '')
    config.registry.expire_after = int(settings.get('aws.expire_after',
                                                    60 * 60 * 24))
    config.registry.buffer_time = int(settings.get('aws.buffer_time',
                                                   600))

    # PYPICLOUD SETTINGS
    config.registry.fallback_url = settings.get('pypi.fallback_url',
                                                'http://pypi.python.org/simple')
    config.registry.use_fallback = asbool(settings.get('pypi.use_fallback',
                                                       True))
    config.registry.prepend_hash = asbool(settings.get('pypi.prepend_hash',
                                                       True))
    config.registry.allow_overwrite = asbool(
        settings.get('pypi.allow_overwrite', False))
    realm = settings.get('pypi.realm', 'pypi')
    config.registry.realm = realm

    # CACHING DATABASE SETTINGS
    db_url = settings.get('pypi.db.url')
    if db_url is None:
        raise ValueError("Must specify a 'pypi.db.url'")
    elif db_url.startswith('redis://'):
        try:
            from redis import StrictRedis
        except ImportError:
            raise ImportError("You must 'pip install redis' before using "
                              "redis as the database")
        config.registry.redis = StrictRedis.from_url(db_url)
        config.add_request_method(_redis_db, name='db', reify=True)
        dbtype = 'redis'
    else:
        engine = engine_from_config(settings, prefix='pypi.db.')
        config.registry.dbmaker = sessionmaker(
            bind=engine, extension=ZopeTransactionExtension())
        config.add_request_method(_db, name='db', reify=True)
        create_schema(engine)
        dbtype = 'sql'

    # Special request methods
    config.add_request_method(lambda x: dbtype, name='dbtype', reify=True)
    config.add_request_method(_bucket, name='bucket', reify=True)
    config.add_request_method(_app_url, name='app_url')

    cache_max_age = int(settings.get('pyramid.cache_max_age', 3600))
    config.add_static_view(name='static/%s' % __version__,
                           path='pypicloud:static',
                           cache_max_age=cache_max_age)


def main(config, **settings):
    """ This function returns a Pyramid WSGI application.
    """
    config = Configurator(settings=settings)
    config.include('pypicloud')
    config.scan(ignore='pypicloud.tests')
    if settings.get('unittest'):
        return config
    return config.make_wsgi_app()
