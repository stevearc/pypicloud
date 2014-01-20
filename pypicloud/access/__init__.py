""" Classes that provide user and package permissions """
from collections import defaultdict
from passlib.apps import custom_app_context as pwd_context
from pyramid.path import DottedNameResolver
from pyramid.security import (Authenticated, Everyone, unauthenticated_userid,
                              effective_principals, Allow, Deny,
                              ALL_PERMISSIONS)
from pyramid.settings import asbool, aslist


class IAccessBackend(object):

    """ Interface for retrieving user and package permission data """

    mutable = False
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
        if principal == 'admin':
            return ['read', 'write']
        if principal.startswith('user:'):
            user = principal[len('user:'):]
            return self.user_permissions(package, user)
        else:
            if principal.startswith('group:'):
                group = principal[len('group:'):]
            elif principal == Everyone:
                group = 'everyone'
            elif principal == Authenticated:
                group = 'authenticated'
            return self.group_permissions(package, group)

    def get_acl(self, package):
        """ Construct an ACL for a package """
        acl = []
        for user, perms in self.user_permissions(package).iteritems():
            for perm in perms:
                acl.append((Allow, 'user:' + user, perm))

        for group, perms in self.group_permissions(package).iteritems():
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
        if self.is_admin(username):
            principals.append('admin')
        for group in self.groups(username):
            principals.append('group:' + group)
        return principals

    def need_admin(self):
        """
        Find out if there are any admin users

        This should only be overridden by mutable backends

        Returns
        -------
        need_admin : bool
            True if no admin user exists and the backend is mutable, False
            otherwise

        """
        return False

    def allow_register(self):
        """
        Check if the backend allows registration

        This should only be overridden by mutable backends

        Returns
        -------
        allow : bool

        """
        return False

    def verify_user(self, username, password):
        """
        Check the login credentials of a user

        For Mutable backends, pending users should fail to verify

        Parameters
        ----------
        username : str
        password : str

        Returns
        -------
        valid : bool
            True if user credentials are valid, false otherwise

        """
        stored_pw = self._get_password_hash(username)
        return stored_pw and pwd_context.verify(password, stored_pw)

    def _get_password_hash(self, username):
        """ Get the stored password hash for a user """
        raise NotImplementedError

    def groups(self, username=None):
        """
        Get a list of all groups

        If a username is specified, get all groups that the user belongs to

        Parameters
        ----------
        username : str, optional

        Returns
        -------
        groups : list
            List of group names

        """
        raise NotImplementedError

    def group_members(self, group):
        """
        Get a list of users that belong to a group

        Parameters
        ----------
        group : str

        Returns
        -------
        users : list
            List of user names

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

    def group_permissions(self, package, group=None):
        """
        Get a mapping of all groups to their permissions on a package

        If a group is specified, just return the list of permissions for that
        group

        Parameters
        ----------
        package : str
            The name of a python package
        group : str, optional
            The name of a single group the check


        Returns
        -------
        permissions : dict
            If group is None, mapping of group name to a list of permissions
            (which can contain 'read' and/or 'write')
        permissions : list
            If group is not None, a list of permissions for that group

        Notes
        -----
        You may specify special groups 'everyone' and/or 'authenticated', which
        correspond to all users and all logged in users respectively.

        """
        raise NotImplementedError

    def user_permissions(self, package, username=None):
        """
        Get a mapping of all users to their permissions for a package

        If a username is specified, just return the list of permissions for
        that user

        Parameters
        ----------
        package : str
            The name of a python package
        username : str
            The name of a single user the check

        Returns
        -------
        permissions : dict
            Mapping of username to a list of permissions (which can contain
            'read' and/or 'write')
        permissions : list
            If username is not None, a list of permissions for that user

        """
        raise NotImplementedError

    def user_package_permissions(self, username):
        """
        Get a list of all packages that a user has permissions on

        Parameters
        ----------
        username : str

        Returns
        -------
        packages : list
            List of dicts. Each dict contains 'package' (str) and 'permissions'
            (list)

        """
        raise NotImplementedError

    def group_package_permissions(self, group):
        """
        Get a list of all packages that a group has permissions on

        Parameters
        ----------
        group : str

        Returns
        -------
        packages : list
            List of dicts. Each dict contains 'package' (str) and 'permissions'
            (list)

        """
        raise NotImplementedError

    def user_data(self, username=None):
        """
        Get a list of all users or data for a single user

        For Mutable backends, this excludes pending users

        Returns
        -------
        users : list
            Each user is a dict with a 'username' str, and 'admin' bool
        user : dict
            If a username is passed in, instead return one user with the fields
            above plus a 'groups' list.

        """
        raise NotImplementedError


class IMutableAccessBackend(IAccessBackend):

    """ Interface for access backends that can change user/group permissions """
    mutable = True

    def need_admin(self):
        for user in self.user_data():
            if user['admin']:
                return False
        return True

    def allow_register(self):
        raise NotImplementedError

    def set_allow_register(self, allow):
        """
        Allow or disallow user registration

        Parameters
        ----------
        allow : bool

        """
        raise NotImplementedError

    def register(self, username, password):
        """
        Register a new user

        The new user should be marked as pending admin approval

        Parameters
        ----------
        username : str
        password : str

        """
        raise NotImplementedError

    def pending_users(self):
        """
        Retrieve a list of all users pending admin approval

        Returns
        -------
        users : list
            List of usernames

        """
        raise NotImplementedError

    def approve_user(self, username):
        """
        Mark a user as approved by the admin

        Parameters
        ----------
        username : str

        """
        raise NotImplementedError

    def edit_user_password(self, username, password):
        """
        Change a user's password

        Parameters
        ----------
        username : str
        password : str

        """
        self._set_password_hash(username, pwd_context.encrypt(password))

    def _set_password_hash(self, username, password_hash):
        """
        Change a user's password

        Parameters
        ----------
        username : str
        password_hash : str
            The hashed password to store

        """
        raise NotImplementedError

    def delete_user(self, username):
        """
        Delete a user

        Parameters
        ----------
        username : str

        """
        raise NotImplementedError

    def set_user_admin(self, username, admin):
        """
        Grant or revoke admin permissions for a user

        Parameters
        ----------
        username : str
        admin : bool
            If True, grant permissions. If False, revoke.

        """
        raise NotImplementedError

    def edit_user_group(self, username, group, add):
        """
        Add or remove a user to/from a group

        Parameters
        ----------
        username : str
        group : str
        add : bool
            If True, add to group. If False, remove.

        """
        raise NotImplementedError

    def create_group(self, group):
        """
        Create a new group

        Parameters
        ----------
        group : str

        """
        raise NotImplementedError

    def delete_group(self, group):
        """
        Delete a group

        Parameters
        ----------
        group : str

        """
        raise NotImplementedError

    def edit_user_permission(self, package, username, perm, add):
        """
        Grant or revoke a permission for a user on a package

        Parameters
        ----------
        package : str
        username : str
        perm : {'read', 'write'}
        add : bool
            If True, grant permissions. If False, revoke.

        """
        raise NotImplementedError

    def edit_group_permission(self, package, group, perm, add):
        """
        Grant or revoke a permission for a group on a package

        Parameters
        ----------
        package : str
        group : str
        perm : {'read', 'write'}
        add : bool
            If True, grant permissions. If False, revoke.

        """
        raise NotImplementedError


class ConfigAccessBackend(IAccessBackend):

    """ Access Backend that uses values set in the config file """

    @classmethod
    def configure(cls, settings):
        super(ConfigAccessBackend, cls).configure(settings)
        cls._settings = settings
        cls.zero_security_mode = asbool(settings.get('auth.zero_security_mode',
                                                     False))
        cls.admins = aslist(settings.get('auth.admins', []))
        cls.user_groups = defaultdict(list)
        cls.group_map = {}

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
            cls.group_map[group_name] = members
            for member in members:
                cls.user_groups[member].append(group_name)

    def _get_password_hash(self, username):
        key = "user.%s" % username
        return self._settings.get(key)

    def groups(self, username=None):
        if username is None:
            return self.group_map.keys()
        else:
            return self.user_groups[username]

    def group_members(self, group):
        return self.group_map.get(group, [])

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

    def group_permissions(self, package, group=None):
        if group is not None:
            key = 'package.%s.group.%s' % (package, group)
            perms = self._perms_from_short(self._settings.get(key))
            if (self.zero_security_mode and group == 'everyone' and
                    'read' not in perms):
                perms.append('read')
            return perms
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

    def user_permissions(self, package, username=None):
        if username is not None:
            key = 'package.%s.user.%s' % (package, username)
            return self._perms_from_short(self._settings.get(key))
        perms = {}
        user_prefix = 'package.%s.user.' % package
        for key, value in self._settings.iteritems():
            if not key.startswith(user_prefix):
                continue
            user = key[len(user_prefix):]
            perms[user] = self._perms_from_short(value)
        return perms

    def get_acl(self, package):
        if self.zero_security_mode:
            return []
        return super(ConfigAccessBackend, self).get_acl(package)

    def user_data(self, username=None):
        if username is not None:
            return {
                'username': username,
                'admin': self.is_admin(username),
                'groups': self.groups(username),
            }
        users = []
        user_prefix = 'user.'
        for key in self._settings:
            if not key.startswith(user_prefix):
                continue
            username = key[len(user_prefix):]
            users.append({
                'username': username,
                'admin': self.is_admin(username)
            })
        return users

    def user_package_permissions(self, username):
        perms = []
        for key, value in self._settings.iteritems():
            pieces = key.split('.')
            if (len(pieces) != 4 or pieces[0] != 'package' or
                    pieces[2] != 'user'):
                continue
            package, user = pieces[1], pieces[3]
            if user == username:
                perms.append({
                    'package': package,
                    'permissions': self._perms_from_short(value),

                })
        return perms

    def group_package_permissions(self, group):
        perms = []
        for key, value in self._settings.iteritems():
            pieces = key.split('.')
            if (len(pieces) != 4 or pieces[0] != 'package' or
                    pieces[2] != 'group'):
                continue
            package, groupname = pieces[1], pieces[3]
            if group == groupname:
                perms.append({
                    'package': package,
                    'permissions': self._perms_from_short(value),

                })
        return perms


class RemoteAccessBackend(IAccessBackend):

    """
    This backend allows you to defer all user auth and permissions to a remote
    server. It requires the ``requests`` package.

    """

    @classmethod
    def configure(cls, settings):
        super(RemoteAccessBackend, cls).configure(settings)
        cls._settings = settings
        cls.server = settings['auth.backend_server']
        cls.auth = None
        user = settings.get('auth.user')
        if user is not None:
            password = settings.get('auth.password')
            cls.auth = (user, password)

    def _req(self, uri, params=None):
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

    def _get_password_hash(self, username):
        # We don't have to do anything here because we overrode 'verify_user'
        pass

    def groups(self, username=None):
        uri = self._settings.get('auth.uri.groups', '/groups')
        params = {}
        if username is not None:
            params['username'] = username
        return self._req(uri, params)

    def group_members(self, group):
        uri = self._settings.get('auth.uri.group_members', '/group_members')
        params = {'group': group}
        return self._req(uri, params)

    def is_admin(self, username):
        uri = self._settings.get('auth.uri.admin', '/admin')
        params = {'username': username}
        return self._req(uri, params)

    def group_permissions(self, package, group=None):
        uri = self._settings.get('auth.uri.group_permissions',
                                 '/group_permissions')
        params = {'package': package}
        if group is not None:
            params['group'] = group
        return self._req(uri, params)

    def user_permissions(self, package, username=None):
        uri = self._settings.get('auth.uri.user_permissions',
                                 '/user_permissions')
        params = {'package': package}
        if username is not None:
            params['username'] = username
        return self._req(uri, params)

    def user_package_permissions(self, username):
        uri = self._settings.get('auth.uri.user_package_permissions',
                                 '/user_package_permissions')
        params = {'username': username}
        return self._req(uri, params)

    def group_package_permissions(self, group):
        uri = self._settings.get('auth.uri.group_package_permissions',
                                 '/group_package_permissions')
        params = {'group': group}
        return self._req(uri, params)

    def user_data(self, username=None):
        uri = self._settings.get('auth.uri.user_data',
                                 '/user_data')
        params = None
        if username is not None:
            params = {'username': username}
        return self._req(uri, params)


def includeme(config):
    """ Configure the app """
    settings = config.get_settings()

    resolver = DottedNameResolver(__name__)
    dotted_name = settings.get('pypi.access_backend', 'config')
    if dotted_name == 'config':
        dotted_name = ConfigAccessBackend
    elif dotted_name == 'remote':
        dotted_name = RemoteAccessBackend
    elif dotted_name == 'sql':
        dotted_name = 'pypicloud.access.sql.SQLAccessBackend'
    access_backend = resolver.maybe_resolve(dotted_name)
    access_backend.configure(settings)
    config.add_request_method(access_backend, name='access', reify=True)
