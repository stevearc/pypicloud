"""LDAP authentication plugin for pypicloud."""
import logging
from collections import namedtuple
from functools import wraps
from pyramid.settings import aslist, asbool

from .base import IAccessBackend
from pypicloud.util import TimedCache


try:
    import ldap
except ImportError:  # pragma: no cover
    raise ImportError(
        "You must 'pip install pypicloud[ldap]' before using ldap as the "
        "authentication backend."
    )


LOG = logging.getLogger(__name__)


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


User = namedtuple('User', ['username', 'dn', 'is_admin'])


class LDAP(object):
    """ Handles interactions with the remote LDAP server """

    def __init__(self, admin_field, admin_value, base_dn, cache_time,
                 service_dn, service_password, service_username, url,
                 user_search_filter, user_dn_format, ignore_cert):
        self._url = url
        self._service_dn = service_dn
        self._service_password = service_password
        self._base_dn = base_dn
        self._user_search_filter = user_search_filter
        self._user_dn_format = user_dn_format
        if user_dn_format is not None:
            if base_dn is not None or user_search_filter is not None:
                raise ValueError("Cannot use user_dn_format with base_dn "
                                 "and user_search_filter")
        else:
            if base_dn is None or user_search_filter is None:
                raise ValueError("Must provide user_dn_format or both base_dn "
                                 "and user_search_filter")
        self._admin_field = admin_field
        self._admin_value = admin_value
        self._server = None
        if cache_time is not None:
            cache_time = int(cache_time)
        self._cache = TimedCache(cache_time, self._fetch_user)
        if service_username is not None:
            self._cache.set_expire(
                service_username,
                User(service_username, service_dn, True),
                None
            )
        self._ignore_cert = ignore_cert

    def connect(self):
        """ Initializes the python-ldap module and does the initial bind """
        if self._ignore_cert:
            ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
        LOG.debug("LDAP connecting to %s", self._url)
        self._server = ldap.initialize(self._url)
        self._bind_to_service()

    def _bind_to_service(self):
        """ Bind to the service account or anonymous """
        if self._service_dn:
            # bind with the service_dn
            self._server.simple_bind_s(self._service_dn, self._service_password)
        else:
            # force a connection without binding
            self._server.whoami_s()

    @reconnect
    def _fetch_user(self, username):
        """ Fetch a user entry from the LDAP server """
        LOG.debug("LDAP fetching user %s", username)
        search_attrs = []
        if self._admin_field is not None:
            search_attrs.append(self._admin_field)
        if self._user_dn_format is not None:
            dn = self._user_dn_format.format(username=username)
            LOG.debug("LDAP searching user %r with dn %r", username, dn)
            results = self._server.search_s(dn, ldap.SCOPE_BASE,
                                            attrlist=search_attrs)
        else:
            search_filter = self._user_search_filter.format(username=username)
            LOG.debug("LDAP searching user %r with filter %r", username,
                      search_filter)
            results = self._server.search_s(
                self._base_dn,
                ldap.SCOPE_SUBTREE,
                search_filter,
                search_attrs,
            )
        if not results:
            LOG.debug("LDAP user %r not found", username)
            return None
        if len(results) > 1:
            raise ValueError("More than one user found for %r: %r" %
                             (username, [r[0] for r in results]))
        dn, attributes = results[0]

        is_admin = False
        if self._admin_field is not None:
            if self._admin_field in attributes:
                is_admin = any((val in attributes[self._admin_field]
                                for val in self._admin_value))

        return User(username, dn, is_admin)

    def get_user(self, username):
        """ Get the User object or None """
        return self._cache.get(username)

    @reconnect
    def verify_user(self, username, password):
        """
        Attempts to bind as the user, then rebinds as service user again
        """
        LOG.debug("LDAP verifying user %s", username)
        # Empty password may successfully complete an anonymous bind.
        # Explicitly disallow empty passwords.
        if password == "":
            return False
        user = self._cache.get(username)
        if user is None:
            return False

        try:
            LOG.debug("LDAP binding user %r", user.dn)
            self._server.simple_bind_s(user.dn, password)
        except ldap.INVALID_CREDENTIALS:
            return False
        else:
            return True
        finally:
            self._bind_to_service()


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
        conn = LDAP(
            admin_field=settings.get('auth.ldap.admin_field'),
            admin_value=aslist(settings.get('auth.ldap.admin_value', [])),
            base_dn=settings.get('auth.ldap.base_dn'),
            cache_time=settings.get('auth.ldap.cache_time'),
            service_dn=settings.get('auth.ldap.service_dn'),
            service_password=settings.get('auth.ldap.service_password', ''),
            service_username=settings.get('auth.ldap.service_username'),
            url=settings['auth.ldap.url'],
            user_dn_format=settings.get('auth.ldap.user_dn_format'),
            user_search_filter=settings.get('auth.ldap.user_search_filter'),
            ignore_cert=asbool(settings.get('auth.ldap.ignore_cert'))
        )
        conn.connect()
        kwargs['conn'] = conn
        return kwargs

    def _get_password_hash(self, *_):  # pragma: no cover
        raise RuntimeError("LDAP should never call _get_password_hash")

    def verify_user(self, username, password):
        return self.conn.verify_user(username, password)

    def groups(self, username=None):
        # We're not supporting groups for LDAP
        return []  # pragma: no cover

    def group_members(self, group):
        # We're not supporting groups for LDAP
        return []  # pragma: no cover

    def is_admin(self, username):
        if not username:
            return False
        user = self.conn.get_user(username)
        return user is not None and user.is_admin

    def group_permissions(self, package):
        return {}

    def user_permissions(self, package):
        return {}

    def user_package_permissions(self, username):
        return []

    def group_package_permissions(self, group):
        return []

    def user_data(self, username=None):
        if username is None:
            return []
        else:
            return {
                "username": username,
                "admin": self.is_admin(username),
                "groups": self.groups(username),
            }
