""" S3-backed pypi server """
import os
import sys
import traceback
import datetime

import logging
from pyramid.config import Configurator
from pyramid.renderers import JSON, render
from pyramid.settings import asbool
from pyramid_beaker import session_factory_from_settings
from six.moves.urllib.parse import urlencode  # pylint: disable=F0401,E0611

from .route import Root
from .util import BetterScrapingLocator


__version__ = '0.4.0'
LOG = logging.getLogger(__name__)


def to_json(value):
    """ A json filter for jinja2 """
    return render('json', value)

json_renderer = JSON()  # pylint: disable=C0103
json_renderer.add_adapter(datetime.datetime, lambda obj, r:
                          float(obj.strftime('%s.%f')))


def _app_url(request, *paths, **params):
    """ Get the base url for the root of the app plus an optional path """
    path = '/'.join(paths)
    if not path.startswith('/'):
        path = '/' + path
    if params:
        path += '?' + urlencode(params)
    return request.application_url + path


def _locator(request):
    """ Get the scraping locator to find packages from the fallback site """
    return BetterScrapingLocator(request.registry.fallback_url)


def includeme(config):
    """ Set up and configure the pypicloud app """
    config.set_root_factory(Root)
    config.include('pyramid_tm')
    config.include('pyramid_beaker')
    config.include('pyramid_duh')
    config.include('pyramid_duh.auth')
    config.include('pypicloud.auth')
    config.include('pypicloud.access')
    config.include('pypicloud.cache')
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
    config.registry.secure_cookie = asbool(settings.get('session.secure',
                                                        False))
    settings.setdefault('session.type', 'cookie')
    settings.setdefault('session.httponly', 'true')
    config.set_session_factory(session_factory_from_settings(settings))

    # PYPICLOUD SETTINGS
    default_url = 'https://pypi.python.org/simple'
    config.registry.fallback_url = settings.get('pypi.fallback_url',
                                                default_url)

    fallback_mode = settings.get('pypi.fallback', 'redirect')
    # Compatibility with the deprecated pypi.use_fallback option
    if 'pypi.fallback' not in settings and 'pypi.use_fallback' in settings:
        LOG.warn("Using deprecated option 'pypi.use_fallback'")
        use_fallback = asbool(settings['pypi.use_fallback'])
        fallback_mode = 'redirect' if use_fallback else 'none'
    always_show_upstream = settings.get('pypi.always_show_upstream')

    # Using fallback=mirror is the same as fallback=cache and
    # always_show_upstream=true
    if always_show_upstream is None:
        always_show_upstream = fallback_mode == 'mirror'
    else:
        always_show_upstream = asbool(always_show_upstream)
    if fallback_mode == 'mirror':
        LOG.warn("pypi.fallback = mirror is deprecated. You can now use "
                 "pypi.fallback = cache and pypi.always_show_upstream = true")
        fallback_mode = 'cache'

    modes = ('redirect', 'cache', 'none')
    if fallback_mode not in modes:
        raise ValueError("Invalid value for 'pypi.fallback'. "
                         "Must be one of %s" % ', '.join(modes))
    config.registry.fallback = fallback_mode
    config.registry.always_show_upstream = always_show_upstream

    # Special request methods
    config.add_request_method(_app_url, name='app_url')
    config.add_request_method(_locator, name='locator', reify=True)
    config.add_request_method(lambda x: __version__, name='pypicloud_version',
                              reify=True)

    cache_max_age = int(settings.get('pyramid.cache_max_age', 3600))
    config.add_static_view(name='static/%s' % __version__,
                           path='pypicloud:static',
                           cache_max_age=cache_max_age)


def traceback_formatter(excpt, value, tback):
    """ Catches all exceptions and re-formats the traceback raised.
    """

    sys.stdout.write("".join(traceback.format_exception(excpt, value, tback)))


def hook_exceptions():
    """ Hooks into the sys module to set our formatter.
    """

    if hasattr(sys.stdout, "fileno"):  # when testing, sys.stdout is StringIO
        # reopen stdout in non buffered mode
        sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)
        # set the hook
        sys.excepthook = traceback_formatter


def main(config, **settings):
    """ This function returns a Pyramid WSGI application.
    """
    hook_exceptions()
    config = Configurator(settings=settings)
    config.include('pypicloud')
    config.scan('pypicloud.views')
    return config.make_wsgi_app()
