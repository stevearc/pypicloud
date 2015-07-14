"""LDAP authentication plugin for pypicloud."""


try:
    import ldap  # pylint: disable=F0401
except ImportError:
    LDAP_ENABLED = False
else:
    LDAP_ENABLED = True

import logging
from functools import wraps

from .base import IAccessBackend


def reconnect(func):
    """If the LDAP connection dies underneath us, recreate it."""

    @wraps(func)
    def _reconnect(*args, **kwargs):
        """Inner wrap function to reconnect on failure."""

        try:
            return func(*args, **kwargs)
        except ldap.LDAPError:
            LDAP._connect()
            return func(*args, **kwargs)

    return _reconnect


class LDAP(object):
    """Handles interactions with the remote LDAP server."""

    @staticmethod
    def configure(settings=None):
        """Configures self with the settings dictionary."""

        LDAP._id_field = settings["auth.ldap.id_field"]
        LDAP._url = settings["auth.ldap.url"]
        LDAP._service_dn = settings["auth.ldap.service_dn"]
        LDAP._service_password = settings["auth.ldap.service_password"]
        LDAP._base_dn = settings["auth.ldap.base_dn"]
        LDAP._all_user_search = settings["auth.ldap.all_user_search"]
        LDAP._admin_field = settings["auth.ldap.admin_field"]
        LDAP._admin_dns = [
            dn for dn in settings["auth.ldap.admin_dns"].splitlines() if dn
        ]

        LDAP._connect()
        LDAP.all_users()

    @staticmethod
    def _connect():
        """Initializes the python-ldap module and does the initial bind."""

        LDAP._server = ldap.initialize(LDAP._url)
        LDAP._server.simple_bind_s(LDAP._service_dn, LDAP._service_password)

    @staticmethod
    @reconnect
    def all_users():
        """Returns a list of all user DNs."""

        if not hasattr(LDAP, "_all_users"):
            results = LDAP._server.search_s(
                LDAP._base_dn,
                ldap.SCOPE_SUBTREE,
                LDAP._all_user_search,
            )
            LDAP._all_users = {}
            for result in results:
                if LDAP._id_field in result[1]:
                    LDAP._all_users[result[1][LDAP._id_field][0]] = result[0]

        return list(LDAP._all_users.values())

    @staticmethod
    def all_usernames():
        """Returns a list of all user names."""

        return list(LDAP._all_users.keys())

    @staticmethod
    @reconnect
    def _add_admins_from_dn(admin_dn):
        """Given a DN fragement, add users to _admins and _admin_usernames."""

        res = LDAP._server.search_s(admin_dn, ldap.SCOPE_SUBTREE)
        try:
            admins = res[0][1][LDAP._admin_field]
        except (IndexError, KeyError) as err:
            logging.warn("Error retrieving admins from %s: %r", admin_dn, err)
            return

        for admin in admins:
            try:
                LDAP._admin_usernames.append(
                    LDAP._server.search_s(
                        admin,
                        ldap.SCOPE_SUBTREE,
                    )[0][1][LDAP._id_field][0]
                )
            except (IndexError, KeyError) as error:
                logging.warn("Error looking up admin %s: %r", admin, error)
            else:
                LDAP._admins.append(admin)

    @staticmethod
    def admins():
        """Returns a list of all the admin DNs."""

        if not hasattr(LDAP, "_admins"):
            LDAP._admins = []
            LDAP._admin_usernames = []
            for admin_dn in LDAP._admin_dns:
                LDAP._add_admins_from_dn(admin_dn)

        return LDAP._admins

    @staticmethod
    def admin_usernames():
        """Returns a list of the admin usernames."""

        if not hasattr(LDAP, "_admin_usernames"):
            LDAP.admins()
        return LDAP._admin_usernames

    @staticmethod
    def user_dn(username):
        """Returns the dn for the username."""

        return LDAP._all_users.get(username)

    @staticmethod
    @reconnect
    def bind_user(user_dn, password):
        """Attempts to bind as the user, then rebinds as service user again."""

        try:
            LDAP._server.simple_bind_s(user_dn, password)
        except ldap.INVALID_CREDENTIALS:
            return False
        else:
            return True
        finally:
            LDAP._connect()


class LDAPAccessBackend(IAccessBackend):
    """
    This backend allows you to store all user and package permissions in a SQL
    database and authenticate against a LDAP server
    """

    DEFAULT_PERMISSIONS = {
        "admin": ("read", "write"),
        "authenticated": ("read", "write"),
        "everyone": ("read",),
    }

    def __init__(self, request=None, **kwargs):
        self.request = request
        super(LDAPAccessBackend, self).__init__(request, **kwargs)

    @classmethod
    def configure(cls, settings):
        kwargs = super(LDAPAccessBackend, cls).configure(settings)
        LDAP.configure(settings)
        return kwargs

    def allow_register(self):
        return False

    def _get_password_hash(self, *_):
        return ""

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
        user_dn = LDAP.user_dn(username)
        return LDAP.bind_user(user_dn, password) if user_dn else False

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
        if username is None or self.is_admin(username):
            return ["admin", "authenticated", "everyone"]
        else:
            return ["authenticated", "everyone"]

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
        if group is "admin":
            return LDAP.admin_usernames()
        elif group in ("authenticated", "everyone"):
            return LDAP.all_usernames()
        else:
            return []

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
        return username in LDAP.admin_usernames()

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
        if group is None:
            return LDAPAccessBackend.DEFAULT_PERMISSIONS
        else:
            return LDAPAccessBackend.DEFAULT_PERMISSIONS.get(group, [])

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
        if username is None:
            return LDAPAccessBackend.DEFAULT_PERMISSIONS
        else:
            perms = set()
            for user_group in self.groups(username):
                perms.update(self.group_permissions(user_group))
            return list(perms)

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
        all_perms = []
        for package in self.request.db.summary():
            all_perms.append({
                "package": package["name"],
                "permissions": self.user_permissions(package, username),
            })
        return all_perms

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
        all_perms = []
        for package in self.request.db.summary():
            all_perms.append({
                "package": package["name"],
                "permissions": self.group_permissions(package, group),
            })
        return all_perms

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
        if username is None:
            users = []
            for user in LDAP.all_usernames():
                users.append({"username": user, "admin": self.is_admin(user)})
            return users
        else:
            return {
                "username": user,
                "admin": self.is_admin(user),
                "groups": self.groups(user),
            }
