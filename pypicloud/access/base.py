""" The access backend object base class """
from collections import defaultdict
from passlib.apps import custom_app_context as pwd_context
from pyramid.security import (Authenticated, Everyone,
                              effective_principals, Allow, Deny,
                              ALL_PERMISSIONS)
from pyramid.settings import aslist


def group_to_principal(group):
    """ Convert a group to its corresponding principal """
    if group in (Everyone, Authenticated) or group.startswith('group:'):
        return group
    elif group == 'everyone':
        return Everyone
    elif group == 'authenticated':
        return Authenticated
    else:
        return 'group:' + group


def groups_to_principals(groups):
    """ Convert a list of groups to a list of principals """
    return [group_to_principal(g) for g in groups]


class IAccessBackend(object):

    """ Base class for retrieving user and package permission data """

    mutable = False
    ROOT_ACL = [
        (Allow, Authenticated, 'login'),
        (Allow, 'admin', ALL_PERMISSIONS),
        (Deny, Everyone, ALL_PERMISSIONS),
    ]

    def __init__(self, request=None, default_read=None, default_write=None,
                 cache_update=None):
        self.request = request
        self.default_read = default_read
        self.default_write = default_write
        self.cache_update = cache_update

    @classmethod
    def configure(cls, settings):
        """ Configure the access backend with app settings """
        return {
            'default_read': aslist(settings.get('pypi.default_read',
                                                ['authenticated'])),
            'default_write': aslist(settings.get('pypi.default_write', [])),
            'cache_update': aslist(settings.get('pypi.cache_update',
                                                ['authenticated'])),
        }

    def allowed_permissions(self, package):
        """
        Get all allowed permissions for all principals on a package

        Returns
        -------
        perms : dict
            Mapping of principal to tuple of permissions

        """
        all_perms = {}
        for user, perms in self.user_permissions(package).iteritems():
            all_perms['user:' + user] = tuple(perms)

        for group, perms in self.group_permissions(package).iteritems():
            all_perms[group_to_principal(group)] = tuple(perms)

        # If there are no group or user specifications for the package, use the
        # default
        if len(all_perms) == 0:
            for principal in groups_to_principals(self.default_read):
                all_perms[principal] = ('read',)
            for principal in groups_to_principals(self.default_write):
                if principal in all_perms:
                    all_perms[principal] += ('write',)
                else:
                    all_perms[principal] = ('write',)
        return all_perms

    def get_acl(self, package):
        """ Construct an ACL for a package """
        acl = []
        permissions = self.allowed_permissions(package)
        for principal, perms in permissions.iteritems():
            for perm in perms:
                acl.append((Allow, principal, perm))
        return acl

    def has_permission(self, package, perm):
        """ Check if this user has a permission for a package """
        current_userid = self.request.userid
        if current_userid is not None and self.is_admin(current_userid):
            return True

        perms = self.allowed_permissions(package)
        for principal in effective_principals(self.request):
            if perm in perms.get(principal, []):
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

    def in_group(self, username, group):
        """
        Find out if a user is in a group

        Parameters
        ----------
        username : str
            Name of user. May be None for the anonymous user.
        group : str
            Name of the group. Supports 'everyone', 'authenticated', and
            'admin'.

        Returns
        -------
        member : bool

        """
        if group in ('everyone', Everyone):
            return True
        elif username is None:
            return False
        elif group in ('authenticated', Authenticated):
            return True
        elif group == 'admin' and self.is_admin(username):
            return True
        else:
            return group in self.groups(username)

    def in_any_group(self, username, groups):
        """
        Find out if a user is in any of a set of groups

        Parameters
        ----------
        username : str
            Name of user. May be None for the anonymous user.
        groups : list
            list of group names. Supports 'everyone', 'authenticated', and
            'admin'.

        Returns
        -------
        member : bool

        """
        return any((self.in_group(username, group) for group in groups))

    def can_update_cache(self):
        """
        Return True if the user has permissions to update the pypi cache
        """
        return self.in_any_group(self.request.userid, self.cache_update)

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
        if self.mutable:
            # if a user is pending, user_data will be None
            user_data = self.user_data(username)
            if user_data is None:
                return False
        return bool(stored_pw and pwd_context.verify(password, stored_pw))

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

        For Mutable backends, this MUST exclude all pending users

        Returns
        -------
        users : list
            Each user is a dict with a 'username' str, and 'admin' bool
        user : dict
            If a username is passed in, instead return one user with the fields
            above plus a 'groups' list.

        """
        raise NotImplementedError

    def dump(self):
        """
        Dump all of the access control data to a universal format

        Returns
        -------
        data : dict

        """
        from pypicloud import __version__
        data = {}
        data['allow_register'] = self.allow_register()
        data['version'] = __version__

        groups = self.groups()
        users = self.user_data()
        for user in users:
            user['password'] = self._get_password_hash(user['username'])

        data['groups'] = {}
        packages = {
            'users': defaultdict(dict),
            'groups': defaultdict(dict),
        }
        for group in groups:
            data['groups'][group] = self.group_members(group)
            perms = self.group_package_permissions(group)
            for perm in perms:
                package = perm['package']
                packages['groups'][package][group] = perm['permissions']

        for user in users:
            username = user['username']
            perms = self.user_package_permissions(username)
            for perm in perms:
                package = perm['package']
                packages['users'][package][username] = perm['permissions']

        # Convert the defaultdict to a dict for easy serialization
        packages['users'] = dict(packages['users'])
        packages['groups'] = dict(packages['groups'])
        data['users'] = users
        data['packages'] = packages
        return data

    def load(self, data):
        """
        Idempotently load universal access control data.

        By default, this does nothing on immutable backends. Backends may
        override this method to provide an implementation.

        This method works by default on mutable backends with no override
        necessary.

        """
        raise TypeError("Access backend '%s' is not mutable and has no "
                        "'load' implementation" % self.__class__.__name__)


class IMutableAccessBackend(IAccessBackend):

    """
    Base class for access backends that can change user/group permissions

    """
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
            This should be the plaintext password

        """
        if self.allow_register():
            self._register(username, pwd_context.encrypt(password))

    def _register(self, username, password):
        """
        Register a new user

        The new user should be marked as pending admin approval

        Parameters
        ----------
        username : str
        password : str
            This will be the hash of the password

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

    def dump(self):
        data = super(IMutableAccessBackend, self).dump()
        pending_users = []
        for username in self.pending_users():  # pylint: disable=E1101
            password = self._get_password_hash(username)
            pending_users.append({
                'username': username,
                'password': password,
            })
        data['pending_users'] = pending_users
        return data

    def load(self, data):
        # Have to temporarily set this as True for the load operation
        self.set_allow_register(True)
        pending_users = set(self.pending_users())

        def user_exists(username):
            """ Helper function that checks if a user already exists """
            return (username in pending_users or
                    self.user_data(username) is not None)

        for user in data['users']:
            if not user_exists(user['username']):
                self._register(user['username'], user['password'])
                self.approve_user(user['username'])
            self.set_user_admin(user['username'], user.get('admin', False))

        for group, members in data['groups'].iteritems():
            if len(self.group_members(group)) == 0:
                self.create_group(group)
            current_members = self.group_members(group)
            add_members = set(members) - set(current_members)
            for member in add_members:
                self.edit_user_group(member, group, True)

        for user in data.get('pending_users', []):
            if not user_exists(user['username']):
                self._register(user['username'], user['password'])

        for package, groups in data['packages']['groups'].iteritems():
            for group, permissions in groups.iteritems():
                for perm in permissions:
                    self.edit_group_permission(package, group, perm, True)

        for package, users in data['packages']['users'].iteritems():
            for user, permissions in users.iteritems():
                for perm in permissions:
                    self.edit_user_permission(package, user, perm, True)

        self.set_allow_register(data['allow_register'])
