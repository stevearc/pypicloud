""" Utilities for authentication and authorization """
import binascii

from paste.httpheaders import AUTHORIZATION
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.security import Everyone, unauthenticated_userid


# Copied from http://docs.pylonsproject.org/projects/pyramid_cookbook/en/latest/auth/basic.html
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

    """

    def authenticated_userid(self, request):
        """ Verify login and return the authed userid """
        credentials = _get_basicauth_credentials(request)
        if credentials is None:
            return None
        userid = credentials['login']
        if request.access.verify_user(credentials['login'],
                                      credentials['password']):
            return userid
        return None

    def effective_principals(self, request):
        """ Get the authed groups for the active user """
        credentials = _get_basicauth_credentials(request)
        if credentials is None:
            return [Everyone]
        userid = credentials['login']
        if request.access.verify_user(userid, credentials['password']):
            return request.access.user_principals(userid)
        return [Everyone]

    def unauthenticated_userid(self, request):
        """ Return userid without performing auth """
        credentials = _get_basicauth_credentials(request)
        if credentials is not None:
            return credentials['login']
        return None

    def remember(self, request, principal, **kw):
        """ HTTP Headers to remember credentials """
        return []

    def forget(self, request):
        """ HTTP headers to forget credentials """
        return []


class SessionAuthPolicy(object):

    """ Simple auth policy using beaker sessions """

    def authenticated_userid(self, request):
        """ Return the authenticated userid or ``None`` if no
        authenticated userid can be found. This method of the policy
        should ensure that a record exists in whatever persistent store is
        used related to the user (the user should not have been deleted);
        if a record associated with the current id does not exist in a
        persistent store, it should return ``None``."""
        return request.session.get('user', None)

    def unauthenticated_userid(self, request):
        """ Return the *unauthenticated* userid.  This method performs the
        same duty as ``authenticated_userid`` but is permitted to return the
        userid based only on data present in the request; it needn't (and
        shouldn't) check any persistent store to ensure that the user record
        related to the request userid exists."""
        return request.session.get('user', None)

    def effective_principals(self, request):
        """ Return a sequence representing the effective principals
        including the userid and any groups belonged to by the current
        user, including 'system' groups such as
        ``pyramid.security.Everyone`` and
        ``pyramid.security.Authenticated``. """
        return request.session.get('principals', [Everyone])

    def remember(self, request, principal, **kw):
        """ Return a set of headers suitable for 'remembering' the
        principal named ``principal`` when set in a response.  An
        individual authentication policy and its consumers can decide
        on the composition and meaning of **kw. """
        request.session['user'] = principal
        request.session['principals'] = \
            request.access.user_principals(principal)
        return []

    def forget(self, request):
        """ Return a set of headers suitable for 'forgetting' the
        current user on subsequent requests. """
        request.session.delete()
        return []


def includeme(config):
    """ Configure the app """
    config.set_authorization_policy(ACLAuthorizationPolicy())
    config.set_authentication_policy(config.registry.authentication_policy)
    config.add_authentication_policy(SessionAuthPolicy())
    config.add_authentication_policy(BasicAuthenticationPolicy())
    config.add_request_method(unauthenticated_userid, name='userid',
                              reify=True)
