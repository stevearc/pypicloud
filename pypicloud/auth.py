""" Utilities for authentication and authorization """
import binascii

from passlib.hash import sha256_crypt  # pylint: disable=E0611
from paste.httpheaders import AUTHORIZATION, WWW_AUTHENTICATE
from pyramid.security import Authenticated, Everyone


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


def auth_callback(credentials, request):
    """ Our callback to authenticate users """
    key = "user.%s" % credentials['login']
    stored_pw = request.registry.settings.get(key)
    if stored_pw and sha256_crypt.verify(credentials['password'], stored_pw):
        return []
    else:
        return None
