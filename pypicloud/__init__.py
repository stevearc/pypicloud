""" S3-backed pypi server """
import boto.s3
from pyramid.path import DottedNameResolver
from boto.s3.key import Key
from pyramid.settings import asbool
from passlib.hash import sha256_crypt  # pylint: disable=E0611
import getpass
import binascii
from paste.httpheaders import AUTHORIZATION
from paste.httpheaders import WWW_AUTHENTICATE
from pyramid.security import (Allow, Deny, Authenticated, Everyone,
                              ALL_PERMISSIONS)
from pyramid.httpexceptions import HTTPBadRequest
import time
from pyramid.config import Configurator
from pyramid.authorization import ACLAuthorizationPolicy
from .models import Package


class Root(dict):

    """ Root context for PyPI Cloud """
    __name__ = __parent__ = None
    __acl__ = [
        (Allow, Authenticated, ALL_PERMISSIONS),
        (Deny, Everyone, ALL_PERMISSIONS),
    ]


# Copied from
# http://docs.pylonsproject.org/projects/pyramid_cookbook/en/latest/auth/basic.html
def _get_basicauth_credentials(request):
    """ Get the user/password from HTTP basic auth """
    authorization = AUTHORIZATION(request.environ)
    try:
        authmeth, auth = authorization.split(' ', 1)
    except ValueError:  # not enough values to unpack
        return None
    if authmeth.lower() == 'basic':
        try:
            auth = auth.strip().decode('base64')
        except binascii.Error:  # can't decode
            return None
        try:
            login, password = auth.split(':', 1)
        except ValueError:  # not enough values to unpack
            return None
        return {'login': login, 'password': password}

    return None


class BasicAuthenticationPolicy(object):

    """ A :app:`Pyramid` :term:`authentication policy` which
    obtains data from basic authentication headers.

    Constructor Arguments

    ``check``

        A callback passed the credentials and the request,
        expected to return None if the userid doesn't exist or a sequence
        of group identifiers (possibly empty) if the user does exist.
        Required.

    ``realm``

        Default: ``Realm``.  The Basic Auth realm string.

    """

    def __init__(self, check, realm='Realm'):
        self.check = check
        self.realm = realm

    def authenticated_userid(self, request):
        """ Verify login and return the authed userid """
        credentials = _get_basicauth_credentials(request)
        if credentials is None:
            return None
        userid = credentials['login']
        if self.check(credentials, request) is not None:  # is not None!
            return userid

    def effective_principals(self, request):
        """ Get the authed groups for the active user """
        effective_principals = [Everyone]
        credentials = _get_basicauth_credentials(request)
        if credentials is None:
            return effective_principals
        userid = credentials['login']
        groups = self.check(credentials, request)
        if groups is None:  # is None!
            return effective_principals
        effective_principals.append(Authenticated)
        effective_principals.append(userid)
        effective_principals.extend(groups)
        return effective_principals

    def unauthenticated_userid(self, request):
        """ Return userid without performing auth """
        creds = _get_basicauth_credentials(request)
        if creds is not None:
            return creds['login']
        return None

    def remember(self, request, principal, **kw):
        """ HTTP Headers to remember credentials """
        return []

    def forget(self, request):
        """ HTTP headers to forget credentials """
        head = WWW_AUTHENTICATE.tuples('Basic realm="%s"' % self.realm)
        return head


def _bucket(request):
    """ Accessor for S3 bucket """
    return request.registry.s3bucket


def _cache(request):
    """ Accessor for ICache object """
    return request.registry.cache


def _packages(request, prefix=''):
    """ Accessor for Packages """
    keys = request.bucket.list(request.registry.prefix + prefix)
    packages = []
    for key in keys:
        pkg = Package.from_path(key.name)
        packages.append(pkg)
    return packages


def _create_url(request, path):
    """ Create or return an HTTP url for an S3 path """
    if request.cache:
        cached_value = request.cache.fetch(request, path)
        if cached_value is not None:
            return cached_value
    key = Key(request.bucket)
    key.key = path
    expire_after = time.time() + request.registry.expire_after
    url = key.generate_url(expire_after, expires_in_absolute=True)
    if request.cache:
        cache_expire_after = expire_after - request.registry.cache_buffer
        request.cache.store(request, path, url, cache_expire_after)
    return url


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


def gen_password():
    """ Generate a salted password """
    password = getpass.getpass()
    verify = getpass.getpass()
    if password != verify:
        print "Passwords do not match!"
    else:
        print sha256_crypt.encrypt(password)


def auth_callback(credentials, request):
    """ Our callback to authenticate users """
    key = "user.%s" % credentials['login']
    stored_pw = request.registry.settings[key]
    if sha256_crypt.verify(credentials['password'], stored_pw):
        return []
    else:
        return None


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
        aws_access_key_id=settings['aws.access_key'],
        aws_secret_access_key=settings['aws.secret_key'])
    config.registry.s3bucket = s3conn.get_bucket(settings['aws.bucket'])

    config.registry.prefix = settings.get('aws.prefix', '')
    config.registry.expire_after = int(settings.get('aws.expire_after',
                                                    60 * 60 * 24))
    config.registry.fallback_url = settings.get('pypi.fallback_url',
                                                'http://pypi.python.org/simple')
    config.registry.use_fallback = asbool(settings.get('pypi.use_fallback',
                                                       True))

    # Configure the cache
    name_resolver = DottedNameResolver(__package__)
    cache_type = settings.get('cache.type')
    if cache_type == 'filesystem':
        cache_type = 'pypicloud.caches.FilesystemCache'
    elif cache_type == 'sqlitedict':
        cache_type = 'pypicloud.caches.SqliteDictCache'

    if cache_type is not None:
        cache_class = name_resolver.resolve(cache_type)
        config.registry.cache = cache_class(settings)
        config.registry.cache_buffer = int(settings.get('cache.buffer_time',
                                                        5 * 60))
    else:
        config.registry.cache = None

    config.add_request_method(_bucket, name='bucket', reify=True)
    config.add_request_method(_cache, name='cache', reify=True)
    config.add_request_method(_packages, name='packages')
    config.add_request_method(_create_url, name='create_url')
    config.add_request_method(_param, name='param')

    # Configure routes
    config.add_route('index', '/')
    config.add_route('simple', '/simple{_:/?}')
    config.add_route('packages', '/packages{_:/?}')
    config.add_route('package_versions', '/simple/{package:[^/]+}{_:/?}')

    config.scan()
    return config.make_wsgi_app()
