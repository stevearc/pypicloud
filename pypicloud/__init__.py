""" S3-backed pypi server """
import binascii

import boto.s3
import getpass
from passlib.hash import sha256_crypt  # pylint: disable=E0611
from paste.httpheaders import AUTHORIZATION, WWW_AUTHENTICATE
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
    if request.db.query(Package).count() == 0:
        keys = request.bucket.list(request.registry.prefix)
        packages = []
        for key in keys:
            pkg = Package.from_path(key.name)
            packages.append(pkg)
            request.db.merge(pkg)
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
