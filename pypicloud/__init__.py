""" S3-backed pypi server """
from pyramid.config import Configurator
from pyramid.renderers import JSON
import datetime
from pyramid.path import DottedNameResolver
from pyramid.renderers import render
from pyramid.settings import asbool
from pyramid_beaker import session_factory_from_settings

from .route import Root


try:
    from ._version import *  # pylint: disable=F0401,W0401
except ImportError:  # pragma: no cover
    __version__ = 'unknown'


def to_json(value):
    """ A json filter for jinja2 """
    return render('json', value)

json_renderer = JSON()  # pylint: disable=C0103
json_renderer.add_adapter(datetime.datetime, lambda obj, r:
                          float(obj.strftime('%s.%f')))


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

    config.add_renderer('json', json_renderer)
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

    # PYPICLOUD SETTINGS
    config.registry.fallback_url = settings.get('pypi.fallback_url',
                                                'http://pypi.python.org/simple')
    config.registry.use_fallback = asbool(settings.get('pypi.use_fallback',
                                                       True))
    realm = settings.get('pypi.realm', 'pypi')
    config.registry.realm = realm

    # CACHING DATABASE SETTINGS
    resolver = DottedNameResolver(__name__)
    dotted_cache = settings.get('pypi.db', 'sql')
    if dotted_cache == 'sql':
        dotted_cache = 'pypicloud.cache.SQLCache'
    elif dotted_cache == 'redis':
        dotted_cache = 'pypicloud.cache.RedisCache'
    cache_impl = resolver.resolve(dotted_cache)

    cache_impl.configure(config)
    cache_impl.reload_if_needed()

    config.add_request_method(cache_impl, name='db', reify=True)

    # Special request methods
    config.add_request_method(_app_url, name='app_url')
    config.add_request_method(lambda x: __version__, name='pypicloud_version',
                              reify=True)

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
    return config.make_wsgi_app()
