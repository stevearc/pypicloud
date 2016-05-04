"""LDAP authentication plugin for pypicloud."""


try:
    import ldap
except ImportError:
    raise ImportError(
        "You must 'pip install pypicloud[ldap]' before using ldap as the "
        "authentication backend."
    )

import logging
from functools import wraps

from .base import IAccessBackend


def reconnect(func):
    """
    If the LDAP connection dies underneath us, recreate it
    """
    @wraps(func)
    def _reconnect(*args, **kwargs):
        """
        Inner wrap function to reconnect on failure
        """
        try:
            return func(*args, **kwargs)
        except ldap.LDAPError:
            LDAP._connect()
            return func(*args, **kwargs)

    return _reconnect


class LDAP(object):
    """
    Handles interactions with the remote LDAP server
    """

    @staticmethod
    def configure(settings=None):
        """
        Configures self with the settings dictionary
        """
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
        LDAP._service_account = settings.get("auth.ldap.service_account")

        LDAP._connect()

    @staticmethod
    def _connect():
        """
        Initializes the python-ldap module and does the initial bind
        """
        LDAP._server = ldap.initialize(LDAP._url)
        LDAP._server.simple_bind_s(LDAP._service_dn, LDAP._service_password)

    @staticmethod
    @reconnect
    def _initialize_cache():
        """
        Retrieve the list of all user names and DNs to cache
        """
        results = LDAP._server.search_s(
            LDAP._base_dn,
            ldap.SCOPE_SUBTREE,
            LDAP._all_user_search,
        )
        LDAP._all_users = {}
        if LDAP._service_account:
            LDAP._all_users[LDAP._service_account] = LDAP._service_dn
        for result in results:
            if LDAP._id_field in result[1]:
                LDAP._all_users[result[1][LDAP._id_field][0]] = result[0]

    @staticmethod
    def all_users():
        """
        Returns a list of all user DNs
        """
        if not hasattr(LDAP, "_all_users"):
            LDAP._initialize_cache()
        return list(set(LDAP._all_users.values()))

    @staticmethod
    def all_usernames():
        """
        Returns a list of all user names
        """
        if not hasattr(LDAP, "_all_users"):
            LDAP._initialize_cache()
        return list(set(LDAP._all_users.keys()))

    @staticmethod
    def user_dn(username):
        """
        Returns the dn for the username
        """
        if not hasattr(LDAP, "_all_users"):
            LDAP._initialize_cache()
        return LDAP._all_users.get(username)

    @staticmethod
    @reconnect
    def _add_admins_from_dn(admin_dn):
        """
        Given a DN fragement, add users to _admins and _admin_usernames
        """
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

        LDAP._admin_usernames = list(set(LDAP._admin_usernames))
        LDAP._admins = list(set(LDAP._admins))

    @staticmethod
    def admins():
        """
        Returns a list of all the admin DNs
        """
        if not hasattr(LDAP, "_admins"):
            LDAP._admins = [LDAP._service_dn]
            LDAP._admin_usernames = []
            if LDAP._service_account:
                LDAP._admin_usernames.append(LDAP._service_account)
            for admin_dn in LDAP._admin_dns:
                LDAP._add_admins_from_dn(admin_dn)

        return LDAP._admins

    @staticmethod
    def admin_usernames():
        """
        Returns a list of the admin usernames
        """
        if not hasattr(LDAP, "_admin_usernames"):
            LDAP.admins()
        return LDAP._admin_usernames

    @staticmethod
    @reconnect
    def bind_user(user_dn, password):
        """
        Attempts to bind as the user, then rebinds as service user again
        """
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
    This backend allows you to authenticate against a remote LDAP server.
    """

    def __init__(self, request=None, group_map=None, **kwargs):
        super(LDAPAccessBackend, self).__init__(request, **kwargs)
        self.group_map = group_map

    @classmethod
    def configure(cls, settings):
        kwargs = super(LDAPAccessBackend, cls).configure(settings)
        LDAP.configure(settings)
        kwargs["group_map"] = {
            "admin": ("read", "write"),
            "authenticated": ("read",),
        }
        for group in kwargs['default_read']:
            kwargs['group_map'][group] = ('read',)
        for group in kwargs['default_write']:
            kwargs['group_map'][group] = ('read', 'write')
        return kwargs

    def allow_register(self):
        return False

    def _get_password_hash(self, *_):
        return ""

    def verify_user(self, username, password):
        """
        Look up the user DN and attempt to bind with the password
        """
        user_dn = LDAP.user_dn(username)
        return LDAP.bind_user(user_dn, password) if user_dn else False

    def groups(self, username=None):
        """
        Get a list of all groups

        If a username is specified, get all groups that the user belongs to
        """
        if username is None or self.is_admin(username):
            return ["admin"]
        else:
            return []

    def group_members(self, group):
        """
        Get a list of users that belong to a group
        """
        if group == "admin":
            return LDAP.admin_usernames()
        elif group in ("authenticated", "everyone"):
            return LDAP.all_usernames()
        else:
            return []

    def is_admin(self, username):
        """
        Check if the user is an admin
        """
        return username in LDAP.admin_usernames()

    def group_permissions(self, package, group=None):
        """
        Get a mapping of all groups to their permissions on a package

        If a group is specified, return the list of permissions for that group
        """
        if group is None:
            return self.group_map
        else:
            return self.group_map.get(group, [])

    def user_permissions(self, package, username=None):
        """
        Get a mapping of all users to their permissions for a package

        If a username is specified, return a list of permissions for that user
        """
        if username is None:
            return self.group_map
        else:
            perms = set()
            for user_group in self.groups(username):
                perms.update(self.group_permissions(user_group))
            return list(perms)

    def user_package_permissions(self, username):
        """
        Get a list of all packages that a user has permissions to
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
        """
        if username is None:
            users = []
            for user in LDAP.all_usernames():
                users.append({"username": user, "admin": self.is_admin(user)})
            return users
        else:
            return {
                "username": username,
                "admin": self.is_admin(username),
                "groups": self.groups(username),
            }
