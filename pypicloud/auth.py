""" Utilities for authentication and authorization """
import binascii

# pylint: disable=E0611
from paste.httpheaders import AUTHORIZATION, WWW_AUTHENTICATE
# pylint: enable=E0611
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.httpexceptions import HTTPForbidden, HTTPUnauthorized
from pyramid.security import Everyone, authenticated_userid


# Copied from
# http://docs.pylonsproject.org/projects/pyramid_cookbook/en/latest/auth/basic.html
def get_basicauth_credentials(request):
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
        credentials = get_basicauth_credentials(request)
        if credentials is None:
            return None
        userid = credentials['login']
        if request.access.verify_user(credentials['login'],
                                      credentials['password']):
            return userid
        return None

    def unauthenticated_userid(self, request):
        """ Return userid without performing auth """
        return request.userid

    def effective_principals(self, request):
        """ Get the authed groups for the active user """
        if request.userid is None:
            return [Everyone]
        return request.access.user_principals(request.userid)

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
        return request.userid

    def effective_principals(self, request):
        """ Return a sequence representing the effective principals
        including the userid and any groups belonged to by the current
        user, including 'system' groups such as
        ``pyramid.security.Everyone`` and
        ``pyramid.security.Authenticated``. """
        if request.userid is None:
            return [Everyone]
        return request.access.user_principals(request.userid)

    def remember(self, request, principal, **_):
        """
        This implementation is slightly different than expected. The
        application should call remember(userid) rather than
        remember(principal)

        """
        request.session['user'] = principal
        return []

    def forget(self, request):
        """ Return a set of headers suitable for 'forgetting' the
        current user on subsequent requests. """
        request.session.delete()
        return []


def _is_logged_in(request):
    """ Check if there is a logged-in user in the session """
    return request.userid is not None


def _request_login(request):
    """ Return a 401 to force pip to upload its HTTP basic auth credentials """
    response = HTTPUnauthorized()
    realm = WWW_AUTHENTICATE.tuples('Basic realm="%s"' %
                                    request.registry.realm)
    response.headers.update(realm)
    return response


def _forbid(request):
    """
    Return a 403 if user is logged in, otherwise return a 401.

    This is required to force pip to upload its HTTP basic auth credentials

    """
    if request.is_logged_in:
        return HTTPForbidden()
    else:
        return _request_login(request)


def includeme(config):
    """ Configure the app """
    config.set_authorization_policy(ACLAuthorizationPolicy())
    config.set_authentication_policy(config.registry.authentication_policy)
    config.add_authentication_policy(SessionAuthPolicy())
    config.add_authentication_policy(BasicAuthenticationPolicy())
    config.add_request_method(authenticated_userid, name='userid',
                              reify=True)
    config.add_request_method(_forbid, name='forbid')
    config.add_request_method(_request_login, name='request_login')
    config.add_request_method(_is_logged_in, name='is_logged_in', reify=True)

    settings = config.get_settings()
    realm = settings.get('pypi.realm', 'pypi')
    config.registry.realm = realm
