""" Utilities for authentication and authorization """
import binascii

from collections import defaultdict
from passlib.hash import sha256_crypt  # pylint: disable=E0611
from paste.httpheaders import AUTHORIZATION
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.security import (Authenticated, Everyone, unauthenticated_userid,
                              effective_principals, Allow)
from pyramid.settings import aslist


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

    """

    def __init__(self, check):
        self.check = check

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
        principals = [Everyone]
        credentials = _get_basicauth_credentials(request)
        if credentials is None:
            return principals
        userid = credentials['login']
        groups = self.check(credentials, request)
        if groups is None:
            return principals
        principals.append(Authenticated)
        principals.append(userid)
        principals.extend(groups)
        return principals

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
        principals = [Everyone]
        userid = self.unauthenticated_userid(request)
        if userid is not None:
            principals.append(Authenticated)
            principals.append(userid)
            if request.is_admin(userid):
                principals.append('admin')
            principals.extend(request.registry.groups[userid])
        return principals

    def remember(self, request, principal, **kw):
        """ Return a set of headers suitable for 'remembering' the
        principal named ``principal`` when set in a response.  An
        individual authentication policy and its consumers can decide
        on the composition and meaning of **kw. """
        request.session['user'] = principal
        return []

    def forget(self, request):
        """ Return a set of headers suitable for 'forgetting' the
        current user on subsequent requests. """
        request.session.delete()
        return []


def auth_callback(credentials, request):
    """ Our callback to authenticate users """
    userid = credentials['login']
    if verify_user(request, userid, credentials['password']):
        principals = []
        if request.is_admin(userid):
            principals.append('admin')
        principals.extend(request.registry.groups[userid])
        return principals
    else:
        return None


def verify_user(request, username, password):
    """ Validate a username/password """
    key = "user.%s" % username
    stored_pw = request.registry.settings.get(key)
    if stored_pw and sha256_crypt.verify(password, stored_pw):
        return True
    else:
        return False


def _package_owner(request, package):
    """ Get the owner of a package """
    settings = request.registry.settings
    key = 'package.%s.owner' % package
    return settings.get(key)


def _has_permission(request, package, perm):
    """ Check if this user has a permission for a package """
    if request.userid is not None:
        if _is_admin(request, request.userid):
            return True
        if request.userid == _package_owner(request, package):
            return True
    for group in effective_principals(request):
        if perm in _group_permission(request, package, group):
            return True
    return False


def _group_permission(request, package, group):
    """ Get the group permissions for a package """
    if group.startswith('group:'):
        group = group[len('group:'):]
    elif group == Everyone:
        group = 'everyone'
    elif group == Authenticated:
        group = 'authenticated'
    settings = request.registry.settings
    key = 'package.%s.group.%s' % (package, group)
    return settings.get(key, '')


def _is_admin(request, user):
    """ Return True if the user is an admin """
    return user in request.registry.admins


def _get_acl(request, package):
    """ Construct an ACL for accessing a package """
    if request.registry.zero_security_mode:
        return []
    settings = request.registry.settings
    acl = []
    key = 'package.%s.owner' % package
    owner = settings.get(key)
    if owner is not None:
        acl.append((Allow, owner, 'read'))
        acl.append((Allow, owner, 'write'))
    group_prefix = 'package.%s.group.' % package
    for key, value in settings.iteritems():
        if not key.startswith(group_prefix):
            continue
        group = key[len(group_prefix):]
        if group == 'everyone':
            group = Everyone
        elif group == 'authenticated':
            group = Authenticated
        else:
            group = 'group:' + group
        if 'r' in value:
            acl.append((Allow, group, 'read'))
        if 'w' in value:
            acl.append((Allow, group, 'write'))
    return acl


def _build_group_map(settings):
    """ Build a mapping of user - list of groups """

    groups = defaultdict(list)

    # Build dict that maps users to list of groups
    for key, value in settings.iteritems():
        if not key.startswith('group.'):
            continue
        group_name = 'group:' + key[len('group.'):]
        members = aslist(value)
        for member in members:
            groups[member].append(group_name)
    return groups


def includeme(config):
    """ Configure the app """
    settings = config.get_settings()
    config.set_authorization_policy(ACLAuthorizationPolicy())
    config.set_authentication_policy(config.registry.authentication_policy)
    config.add_authentication_policy(SessionAuthPolicy())
    config.add_authentication_policy(BasicAuthenticationPolicy(auth_callback))
    config.add_request_method(unauthenticated_userid, name='userid',
                              reify=True)
    config.add_request_method(_is_admin, name='is_admin')
    config.add_request_method(_has_permission, name='has_permission')
    config.add_request_method(_get_acl, name='get_acl')
    config.registry.groups = _build_group_map(settings)
