"""LDAP authentication plugin for pypicloud."""
import logging
from functools import wraps
from pyramid.settings import aslist

from .base import IAccessBackend


try:
    import ldap
except ImportError:  # pragma: no cover
    raise ImportError(
        "You must 'pip install pypicloud[ldap]' before using ldap as the "
        "authentication backend."
    )


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
        LDAP._admin_dns = aslist(settings["auth.ldap.admin_dns"])
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
        for dn, attributes in results:
            if LDAP._id_field in attributes:
                LDAP._all_users[attributes[LDAP._id_field][0]] = dn

    @staticmethod
    def clear_cache():
        """ Clear the cached data """
        if hasattr(LDAP, '_all_users'):
            del LDAP._all_users
        if hasattr(LDAP, '_admins'):
            del LDAP._admins
        if hasattr(LDAP, '_admin_usernames'):
            del LDAP._admin_usernames

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
        res = LDAP._server.search_s(admin_dn, ldap.SCOPE_BASE)
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
                        ldap.SCOPE_BASE,
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
        # Empty password may successfully complete an anonymous bind.
        # Explicitly disallow empty passwords.
        if password == "":
            return False

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

    @classmethod
    def configure(cls, settings):
        kwargs = super(LDAPAccessBackend, cls).configure(settings)
        LDAP.configure(settings)
        return kwargs

    def _get_password_hash(self, *_):  # pragma: no cover
        raise RuntimeError("LDAP should never call _get_password_hash")

    def verify_user(self, username, password):
        user_dn = LDAP.user_dn(username)
        return LDAP.bind_user(user_dn, password) if user_dn else False

    def groups(self, username=None):
        # We're not supporting groups for LDAP
        return []  # pragma: no cover

    def group_members(self, group):
        # We're not supporting groups for LDAP
        return []  # pragma: no cover

    def is_admin(self, username):
        return username in LDAP.admin_usernames()

    def group_permissions(self, package, group=None):
        if group is None:
            return {}
        else:
            return []

    def user_permissions(self, package, username=None):
        if username is None:
            return {}
        else:
            return []

    def user_package_permissions(self, username):
        return []

    def group_package_permissions(self, group):
        return []

    def user_data(self, username=None):
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

    def clear_cache(self):
        """ Clear the cached LDAP data """
        LDAP.clear_cache()
