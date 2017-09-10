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
    def _reconnect(self, *args, **kwargs):
        """
        Inner wrap function to reconnect on failure
        """
        try:
            return func(self, *args, **kwargs)
        except ldap.LDAPError:
            self.connect()
            return func(*args, **kwargs)

    return _reconnect


class LDAP(object):
    """ Handles interactions with the remote LDAP server """

    def __init__(self, id_field, url, service_dn, service_password, base_dn,
                 all_user_search, admin_field, admin_dns, service_account):
        self._id_field = id_field
        self._url = url
        self._service_dn = service_dn
        self._service_password = service_password
        self._base_dn = base_dn
        self._all_user_search = all_user_search
        self._admin_field = admin_field
        self._admin_dns = admin_dns
        self._service_account = service_account
        self._server = None
        self._all_users = None
        self._admins = None
        self._admin_usernames = None

    def connect(self):
        """ Initializes the python-ldap module and does the initial bind """
        self._server = ldap.initialize(self._url)
        self._server.simple_bind_s(self._service_dn, self._service_password)

    @reconnect
    def _initialize_cache(self):
        """ Retrieve the list of all user names and DNs to cache """
        results = self._server.search_s(
            self._base_dn,
            ldap.SCOPE_SUBTREE,
            self._all_user_search,
        )
        self._all_users = {}
        if self._service_account:
            self._all_users[self._service_account] = self._service_dn
        for dn, attributes in results:
            if self._id_field in attributes:
                self._all_users[attributes[self._id_field][0]] = dn

    def all_usernames(self):
        """ Returns a list of all user names """
        if self._all_users is None:
            self._initialize_cache()
        return list(set(self._all_users.keys()))

    def user_dn(self, username):
        """ Returns the dn for the username """
        if self._all_users is None:
            self._initialize_cache()
        return self._all_users.get(username)

    @reconnect
    def _add_admins_from_dn(self, admin_dn):
        """
        Given a DN fragement, add users to _admins and _admin_usernames
        """
        res = self._server.search_s(admin_dn, ldap.SCOPE_BASE)
        try:
            admins = res[0][1][self._admin_field]
        except (IndexError, KeyError) as err:
            logging.warn("Error retrieving admins from %s: %r", admin_dn, err)
            return

        for admin in admins:
            try:
                self._admin_usernames.append(
                    self._server.search_s(
                        admin,
                        ldap.SCOPE_BASE,
                    )[0][1][self._id_field][0]
                )
            except (IndexError, KeyError) as error:
                logging.warn("Error looking up admin %s: %r", admin, error)
            else:
                self._admins.append(admin)

        self._admin_usernames = list(set(self._admin_usernames))
        self._admins = list(set(self._admins))

    def admins(self):
        """ Returns a list of all the admin DNs """
        if self._admins is None:
            self._admins = [self._service_dn]
            self._admin_usernames = []
            if self._service_account:
                self._admin_usernames.append(self._service_account)
            for admin_dn in self._admin_dns:
                self._add_admins_from_dn(admin_dn)

        return self._admins

    def admin_usernames(self):
        """ Returns a list of the admin usernames """
        if self._admin_usernames is None:
            self.admins()
        return self._admin_usernames

    @reconnect
    def bind_user(self, user_dn, password):
        """
        Attempts to bind as the user, then rebinds as service user again
        """
        # Empty password may successfully complete an anonymous bind.
        # Explicitly disallow empty passwords.
        if password == "":
            return False

        try:
            self._server.simple_bind_s(user_dn, password)
        except ldap.INVALID_CREDENTIALS:
            return False
        else:
            return True
        finally:
            self.connect()


class LDAPAccessBackend(IAccessBackend):
    """
    This backend allows you to authenticate against a remote LDAP server.
    """
    def __init__(self, request=None, conn=None, **kwargs):
        super(LDAPAccessBackend, self).__init__(request, **kwargs)
        self.conn = conn

    @classmethod
    def configure(cls, settings):
        kwargs = super(LDAPAccessBackend, cls).configure(settings)
        ldap_args = {}
        ldap_args['admin_dns'] = aslist(settings["auth.ldap.admin_dns"])
        ldap_args['admin_field'] = settings["auth.ldap.admin_field"]
        ldap_args['all_user_search'] = settings["auth.ldap.all_user_search"]
        ldap_args['base_dn'] = settings["auth.ldap.base_dn"]
        ldap_args['id_field'] = settings.get("auth.ldap.id_field", 'cn')
        ldap_args['service_account'] = settings.get("auth.ldap.service_account")
        ldap_args['service_dn'] = settings["auth.ldap.service_dn"]
        ldap_args['service_password'] = settings.get("auth.ldap.service_password", '')
        ldap_args['url'] = settings["auth.ldap.url"]

        conn = LDAP(**ldap_args)
        conn.connect()
        kwargs['conn'] = conn
        return kwargs

    def _get_password_hash(self, *_):  # pragma: no cover
        raise RuntimeError("LDAP should never call _get_password_hash")

    def verify_user(self, username, password):
        user_dn = self.conn.user_dn(username)
        return self.conn.bind_user(user_dn, password) if user_dn else False

    def groups(self, username=None):
        # We're not supporting groups for LDAP
        return []  # pragma: no cover

    def group_members(self, group):
        # We're not supporting groups for LDAP
        return []  # pragma: no cover

    def is_admin(self, username):
        return username in self.conn.admin_usernames()

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
            for user in self.conn.all_usernames():
                users.append({"username": user, "admin": self.is_admin(user)})
            return users
        else:
            return {
                "username": username,
                "admin": self.is_admin(username),
                "groups": self.groups(username),
            }
