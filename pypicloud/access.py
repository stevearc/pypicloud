""" Classes that provide user and package permissions """
from collections import defaultdict
from passlib.hash import sha256_crypt  # pylint: disable=E0611
from pyramid.path import DottedNameResolver
from pyramid.security import (Authenticated, Everyone, unauthenticated_userid,
                              effective_principals, Allow, Deny,
                              ALL_PERMISSIONS)
from pyramid.settings import asbool, aslist


class IAccessBackend(object):

    """ Interface for retrieving user and package permission data """

    ROOT_ACL = [
        (Allow, Authenticated, 'login'),
        (Allow, 'admin', ALL_PERMISSIONS),
        (Deny, Everyone, ALL_PERMISSIONS),
    ]

    def __init__(self, request):
        self.request = request

    @classmethod
    def configure(cls, settings):
        """ Configure the access backend with app settings """

    def verify_user(self, username, password):
        """
        Check the login credentials of a user

        Parameters
        ----------
        username : str
        password : str

        Returns
        -------
        valid : bool
            True if user credentials are valid, false otherwise

        """
        raise NotImplementedError

    def user_principals(self, username):
        """
        Get a list of principals for a user

        Parameters
        ----------
        username : str

        Returns
        -------
        principals : list

        """
        principals = ['user:' + username, Everyone, Authenticated]
        current_userid = unauthenticated_userid(self.request)
        if current_userid is not None and self.is_admin(current_userid):
            principals.append('admin')
        for group in self.user_groups(username):
            principals.append('group:' + group)
        return principals

    def user_groups(self, username):
        """
        Get a list of groups that a user belongs to

        Parameters
        ----------
        username : str

        Returns
        -------
        groups : list

        """
        raise NotImplementedError

    def is_admin(self, username):
        """
        Check if the user is an admin

        Parameters
        ----------
        username : str

        Returns
        -------
        is_admin : bool

        """
        raise NotImplementedError

    def principal_permissions(self, package, principal):
        """
        Get the list of permissions a principal has for a package

        Parameters
        ----------
        package : str
            The name of a python package managed by pypicloud
        principal : str
            The name of the principal

        Returns
        -------
        permissions : list
            The list may contain 'read' and/or 'write', or it may be empty.

        """
        if principal.startswith('user:'):
            user = principal[len('user:'):]
            return self.all_user_permissions(package).get(user, [])
        else:
            if principal.startswith('group:'):
                group = principal[len('group:'):]
            elif principal == Everyone:
                group = 'everyone'
            elif principal == Authenticated:
                group = 'authenticated'
            return self.all_group_permissions(package).get(group, [])

    def all_group_permissions(self, package):
        """
        Get a mapping of all groups to their permissions for a package

        Parameters
        ----------
        package : str
            The name of a python package

        Returns
        -------
        permissions : dict
            Mapping of group name to a list of permissions (which can contain
            'read' and/or 'write')

        Notes
        -----
        You may specify special groups 'everyone' and/or 'authenticated', which
        correspond to all users and all logged in users respectively.

        """
        raise NotImplementedError

    def all_user_permissions(self, package):
        """
        Get a mapping of all users to their permissions for a package

        Parameters
        ----------
        package : str
            The name of a python package

        Returns
        -------
        permissions : dict
            Mapping of username to a list of permissions (which can contain
            'read' and/or 'write')

        """
        raise NotImplementedError

    def get_acl(self, package):
        """ Construct an ACL for a package """
        acl = []
        for user, perms in self.all_user_permissions(package).iteritems():
            for perm in perms:
                acl.append((Allow, 'user:' + user, perm))

        for group, perms in self.all_group_permissions(package).iteritems():
            if group == 'everyone':
                group = Everyone
            elif group == 'authenticated':
                group = Authenticated
            else:
                group = 'group:' + group
            for perm in perms:
                acl.append((Allow, group, perm))
        return acl

    def has_permission(self, package, perm):
        """ Check if this user has a permission for a package """
        current_userid = unauthenticated_userid(self.request)
        if current_userid is not None and self.is_admin(current_userid):
            return True
        for principal in effective_principals(self.request):
            if perm in self.principal_permissions(package, principal):
                return True
        return False


class ConfigAccessBackend(IAccessBackend):

    """ Access Backend that uses values set in the config file """

    @classmethod
    def configure(cls, settings):
        cls._settings = settings
        cls.zero_security_mode = asbool(settings.get('auth.zero_security_mode',
                                                     False))
        cls.admins = aslist(settings.get('auth.admins', []))
        cls.groups = defaultdict(list)

        if cls.zero_security_mode:
            cls.ROOT_ACL = [
                (Allow, Everyone, 'login'),
                (Allow, Everyone, 'read'),
                (Allow, Authenticated, 'write'),
                (Allow, 'admin', ALL_PERMISSIONS),
                (Deny, Everyone, ALL_PERMISSIONS),
            ]
        else:
            cls.ROOT_ACL = IAccessBackend.ROOT_ACL

        # Build dict that maps users to list of groups
        for key, value in settings.iteritems():
            if not key.startswith('group.'):
                continue
            group_name = key[len('group.'):]
            members = aslist(value)
            for member in members:
                cls.groups[member].append(group_name)

    def verify_user(self, username, password):
        key = "user.%s" % username
        stored_pw = self._settings.get(key)
        if stored_pw and sha256_crypt.verify(password, stored_pw):
            return True
        else:
            return False

    def user_groups(self, username):
        return self.groups[username]

    def is_admin(self, username):
        return username in self.admins

    @staticmethod
    def _perms_from_short(value):
        """ Convert a 'r' or 'rw' specification to a list of permissions """
        value = value or ''
        perms = []
        if 'r' in value:
            perms.append('read')
        if 'w' in value:
            perms.append('write')
        return perms

    def all_group_permissions(self, package):
        perms = {}
        group_prefix = 'package.%s.group.' % package
        for key, value in self._settings.iteritems():
            if not key.startswith(group_prefix):
                continue
            group = key[len(group_prefix):]
            perms[group] = self._perms_from_short(value)
        if self.zero_security_mode:
            perms.setdefault('everyone', [])
            if 'read' not in perms['everyone']:
                perms['everyone'].append('read')
        return perms

    def all_user_permissions(self, package):
        perms = {}
        user_prefix = 'package.%s.user.' % package
        for key, value in self._settings.iteritems():
            if not key.startswith(user_prefix):
                continue
            group = key[len(user_prefix):]
            perms[group] = self._perms_from_short(value)
        return perms

    def get_acl(self, package):
        if self.zero_security_mode:
            return []
        return super(ConfigAccessBackend, self).get_acl(package)


class RemoteAccessBackend(IAccessBackend):

    """
    This backend allows you to defer all user auth and permissions to a remote
    server. It requires the ``requests`` package.

    """

    @classmethod
    def configure(cls, settings):
        cls._settings = settings
        cls.server = settings['auth.backend_server']
        cls.auth = None
        user = settings.get('auth.user')
        if user is not None:
            password = settings.get('auth.password')
            cls.auth = (user, password)

    def _req(self, uri, params):
        """ Hit a server endpoint and return the json response """
        import requests
        response = requests.get(self.server + uri, params=params,
                                auth=self.auth)
        response.raise_for_status()
        return response.json()

    def verify_user(self, username, password):
        uri = self._settings.get('auth.uri.verify', '/verify')
        params = {'username': username, 'password': password}
        return self._req(uri, params)

    def user_groups(self, username):
        uri = self._settings.get('auth.uri.groups', '/groups')
        params = {'username': username}
        return self._req(uri, params)

    def is_admin(self, username):
        uri = self._settings.get('auth.uri.admin', '/admin')
        params = {'username': username}
        return self._req(uri, params)

    def all_group_permissions(self, package):
        uri = self._settings.get('auth.uri.group_permissions',
                                 '/group_permissions')
        params = {'package': package}
        return self._req(uri, params)

    def all_user_permissions(self, package):
        uri = self._settings.get('auth.uri.user_permissions',
                                 '/user_permissions')
        params = {'package': package}
        return self._req(uri, params)


def includeme(config):
    """ Configure the app """
    settings = config.get_settings()

    resolver = DottedNameResolver(__name__)
    access_backend = resolver.maybe_resolve(
        settings.get('pypi.access_backend', ConfigAccessBackend))
    access_backend.configure(settings)
    config.add_request_method(access_backend, name='access', reify=True)
