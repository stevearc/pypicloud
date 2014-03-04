""" The access backend object base class """
from passlib.apps import custom_app_context as pwd_context
from pyramid.security import (Authenticated, Everyone, unauthenticated_userid,
                              effective_principals, Allow, Deny,
                              ALL_PERMISSIONS)


class IAccessBackend(object):

    """ Base class for retrieving user and package permission data """

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
