""" Utilities for authentication and authorization """
import binascii
from base64 import b64decode

# pylint: disable=E0611
from paste.httpheaders import AUTHORIZATION, WWW_AUTHENTICATE

# pylint: enable=E0611
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.httpexceptions import HTTPForbidden, HTTPUnauthorized
from pyramid.interfaces import ISecurityPolicy
from pyramid.security import Allowed, Denied
from zope.interface import implementer


# Copied from
# http://docs.pylonsproject.org/projects/pyramid_cookbook/en/latest/auth/basic.html
def get_basicauth_credentials(request):
    """Get the user/password from HTTP basic auth"""
    authorization = AUTHORIZATION(request.environ)
    try:
        authmeth, auth = authorization.split(" ", 1)
    except ValueError:  # not enough values to unpack
        return None
    if authmeth.lower() == "basic":
        try:
            auth = b64decode(auth.strip()).decode("utf8")
        except (TypeError, binascii.Error):  # can't decode
            return None
        try:
            login, password = auth.split(":", 1)
        except ValueError:  # not enough values to unpack
            return None
        return {"login": login, "password": password}

    return None


@implementer(ISecurityPolicy)
class PypicloudSecurityPolicy:
    def __init__(self):
        self.acl_policy = ACLAuthorizationPolicy()

    def identity(self, request):
        """Return the :term:`identity` of the current user.  The object can be
        of any shape, such as a simple ID string or an ORM object.
        """
        # First try fetching from the session
        userid = request.session.get("user", None)
        if userid is not None:
            return userid
        # Then fall back to HTTP basic auth
        credentials = get_basicauth_credentials(request)
        if credentials is None:
            return None
        userid = credentials["login"]
        if request.access.verify_user(userid, credentials["password"]):
            return userid
        return None

    def authenticated_userid(self, request):
        """Return a :term:`userid` string identifying the trusted and
        verified user, or ``None`` if unauthenticated.

        If the result is ``None``, then
        :attr:`pyramid.request.Request.is_authenticated` will return ``False``.
        """
        return self.identity(request)

    def permits(self, request, context, permission):
        """Return an instance of :class:`pyramid.security.Allowed` if a user
        of the given identity is allowed the ``permission`` in the current
        ``context``, else return an instance of
        :class:`pyramid.security.Denied`.
        """
        if isinstance(context, str):
            # We assume that context is the name of a package
            if request.access.has_permission(context, permission):
                return Allowed("Allowed by ACL")
            return Denied("Permission not granted")
        else:
            userid = self.authenticated_userid(request)
            principals = request.access.user_principals(userid)
            return self.acl_policy.permits(context, principals, permission)

    def remember(self, request, userid, **kw):
        """Return a set of headers suitable for 'remembering' the
        :term:`userid` named ``userid`` when set in a response.  An individual
        security policy and its consumers can decide on the composition and
        meaning of ``**kw``.
        """
        request.session["user"] = userid
        return []

    def forget(self, request, **kw):
        """Return a set of headers suitable for 'forgetting' the
        current user on subsequent requests.  An individual security policy and
        its consumers can decide on the composition and meaning of ``**kw``.
        """
        request.session.delete()
        return []


def _request_login(request):
    """Return a 401 to force pip to upload its HTTP basic auth credentials"""
    response = HTTPUnauthorized()
    realm = WWW_AUTHENTICATE.tuples('Basic realm="%s"' % request.registry.realm)
    response.headers.update(realm)
    return response


def _forbid(request):
    """
    Return a 403 if user is logged in, otherwise return a 401.

    This is required to force pip to upload its HTTP basic auth credentials

    """
    if request.is_authenticated:
        return HTTPForbidden()
    else:
        return _request_login(request)


def includeme(config):
    """Configure the app"""
    config.set_security_policy(PypicloudSecurityPolicy())
    config.add_request_method(_forbid, name="forbid")
    config.add_request_method(_request_login, name="request_login")

    settings = config.get_settings()
    config.registry.realm = settings.get("pypi.realm", "pypi")
