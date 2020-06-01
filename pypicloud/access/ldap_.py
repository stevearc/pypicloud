"""LDAP authentication plugin for pypicloud."""
import logging
from collections import namedtuple
from functools import wraps

from pyramid.settings import asbool, aslist

from pypicloud.util import TimedCache

from .base import IAccessBackend
from .config import ConfigAccessBackend

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
            return func(self, *args, **kwargs)

    return _reconnect


User = namedtuple("User", ["username", "dn", "is_admin"])


class LDAP(object):
    """ Handles interactions with the remote LDAP server """

    def __init__(
        self,
        admin_field,
        admin_group_dn,
        admin_value,
        base_dn,
        cache_time,
        service_dn,
        service_password,
        service_username,
        url,
        user_search_filter,
        user_dn_format,
        ignore_cert,
        ignore_referrals,
        ignore_multiple_results,
    ):
        self._url = url
        self._service_dn = service_dn
        self._service_password = service_password
        self._base_dn = base_dn
        self._user_search_filter = user_search_filter
        self._user_dn_format = user_dn_format
        if user_dn_format is not None:
            if base_dn is not None or user_search_filter is not None:
                raise ValueError(
                    "Cannot use user_dn_format with base_dn " "and user_search_filter"
                )
        else:
            if base_dn is None or user_search_filter is None:
                raise ValueError(
                    "Must provide user_dn_format or both base_dn "
                    "and user_search_filter"
                )
        self._admin_field = admin_field
        self._admin_group_dn = admin_group_dn
        if admin_group_dn and not self._user_dn_format:
            raise ValueError(
                "ldap.admin_group_dn must be used with ldap.user_dn_format"
            )
        self._admin_value = set(admin_value)
        self._server = None
        if cache_time is not None:
            cache_time = int(cache_time)
        self._cache = TimedCache(cache_time, self._fetch_user)
        if service_username is not None:
            self._cache.set_expire(
                service_username, User(service_username, service_dn, True), None
            )
        self._ignore_cert = ignore_cert
        self._ignore_referrals = ignore_referrals
        self._ignore_multiple_results = ignore_multiple_results
        self._admin_member_type = None

    def connect(self):
        """ Initializes the python-ldap module and does the initial bind """
        if self._ignore_cert:
            ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
        if self._ignore_referrals:
            ldap.set_option(ldap.OPT_REFERRALS, ldap.OPT_OFF)
        LOG.debug("LDAP connecting to %s", self._url)
        self._server = ldap.initialize(self._url, bytes_mode=False)
        self._bind_to_service()

    @property
    def admin_member_type(self):
        if self._admin_member_type is None:
            LOG.debug("Fetching admin group %s", self._admin_group_dn)
            try:
                results = self._server.search_s(
                    self._admin_group_dn, ldap.SCOPE_BASE, attrlist=["objectClass"]
                )
            except ldap.NO_SUCH_OBJECT as e:
                LOG.debug("NO_SUCH_OBJECT %s", e)
                return "member"
            dn, attributes = results[0]
            classes = [self._decode_attribute(x) for x in attributes["objectClass"]]
            if "groupOfUniqueNames" in classes:
                self._admin_member_type = "uniqueMember"
            else:
                self._admin_member_type = "member"
        return self._admin_member_type

    def _bind_to_service(self):
        """ Bind to the service account or anonymous """
        if self._service_dn:
            # bind with the service_dn
            self._server.simple_bind_s(self._service_dn, self._service_password)
        else:
            # force a connection without binding
            self._server.whoami_s()

    @reconnect
    def test_connection(self):
        """ Binds to service. Will throw if bad connection """
        self._bind_to_service()

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
            try:
                results = self._server.search_s(
                    dn, ldap.SCOPE_BASE, attrlist=search_attrs
                )
            except ldap.NO_SUCH_OBJECT as e:
                LOG.debug("NO_SUCH_OBJECT %s", e)
                return
        else:
            search_filter = self._user_search_filter.format(username=username)
            LOG.debug("LDAP searching user %r with filter %r", username, search_filter)
            try:
                results = self._server.search_s(
                    self._base_dn, ldap.SCOPE_SUBTREE, search_filter, search_attrs
                )
            except ldap.NO_SUCH_OBJECT as e:
                LOG.debug("NO_SUCH_OBJECT %s", e)
                return
            except ldap.NO_RESULTS_RETURNED as e:
                LOG.debug("NO_RESULTS_RETURNED %s", e)
                return
        if not results:
            LOG.debug("LDAP user %r not found", username)
            return None
        if len(results) > 1:
            err_msg = "More than one user found for %r: %r" % (
                username,
                [r[0] for r in results],
            )
            if self._ignore_multiple_results:
                LOG.warning(err_msg)
            else:
                raise ValueError(err_msg)
        dn, attributes = results[0]
        LOG.debug("dn: %r, attributes %r", dn, attributes)

        is_admin = False
        if self._admin_field is not None:
            if self._admin_field in attributes:
                is_admin = bool(
                    self._admin_value.intersection(
                        [
                            self._decode_attribute(x)
                            for x in attributes[self._admin_field]
                        ]
                    )
                )
        if not is_admin and self._admin_group_dn:
            user_dn = self._user_dn_format.format(username=username)
            search_filter = "(%s=%s)" % (self.admin_member_type, user_dn)
            LOG.debug(
                "Searching admin group %s for %s", self._admin_group_dn, search_filter
            )
            try:
                results = self._server.search_s(
                    self._admin_group_dn, ldap.SCOPE_BASE, search_filter
                )
            except ldap.NO_SUCH_OBJECT as e:
                LOG.debug("NO_SUCH_OBJECT %s", e)
            else:
                is_admin = bool(results)

        return User(username, dn, is_admin)

    def _decode_attribute(self, attribute):
        if attribute and hasattr(attribute, "decode"):
            decoded = attribute.decode("utf-8")
            return decoded
        else:
            return attribute

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

    def __init__(self, request=None, conn=None, fallback_factory=None, **kwargs):
        super(LDAPAccessBackend, self).__init__(request, **kwargs)
        self.conn = conn
        self._fallback = None
        self._fallback_factory = fallback_factory

    @property
    def fallback(self):
        if self._fallback is None and self._fallback_factory is not None:
            self._fallback = self._fallback_factory(self.request)
        return self._fallback

    @classmethod
    def configure(cls, settings):
        kwargs = super(LDAPAccessBackend, cls).configure(settings)
        conn = LDAP(
            admin_field=settings.get("auth.ldap.admin_field"),
            admin_group_dn=settings.get("auth.ldap.admin_group_dn"),
            admin_value=aslist(
                settings.get("auth.ldap.admin_value", []), flatten=False
            ),
            base_dn=settings.get("auth.ldap.base_dn"),
            cache_time=settings.get("auth.ldap.cache_time"),
            service_dn=settings.get("auth.ldap.service_dn"),
            service_password=settings.get("auth.ldap.service_password", ""),
            service_username=settings.get("auth.ldap.service_username"),
            url=settings["auth.ldap.url"],
            user_dn_format=settings.get("auth.ldap.user_dn_format"),
            user_search_filter=settings.get("auth.ldap.user_search_filter"),
            ignore_cert=asbool(settings.get("auth.ldap.ignore_cert")),
            ignore_referrals=asbool(settings.get("auth.ldap.ignore_referrals", False)),
            ignore_multiple_results=asbool(
                settings.get("auth.ldap.ignore_multiple_results", False)
            ),
        )
        conn.connect()
        kwargs["conn"] = conn

        fallback = settings.get("auth.ldap.fallback")
        if fallback == "config":
            kw = ConfigAccessBackend.configure(settings)
            kwargs["fallback_factory"] = lambda r: ConfigAccessBackend(r, **kw)

        return kwargs

    def _get_password_hash(self, *_):  # pragma: no cover
        raise RuntimeError("LDAP should never call _get_password_hash")

    def verify_user(self, username, password):
        return self.conn.verify_user(username, password)

    def groups(self, username=None):
        if self.fallback is not None:
            return self.fallback.groups(username)
        # LDAP doesn't support groups by default
        return []

    def group_members(self, group):
        if self.fallback is not None:
            return self.fallback.group_members(group)
        # LDAP doesn't support groups by default
        return []

    def is_admin(self, username):
        if not username:
            return False
        user = self.conn.get_user(username)
        return user is not None and user.is_admin

    def group_permissions(self, package):
        if self.fallback is not None:
            return self.fallback.group_permissions(package)
        return {}

    def user_permissions(self, package):
        if self.fallback is not None:
            return self.fallback.user_permissions(package)
        return {}

    def user_package_permissions(self, username):
        if self.fallback is not None:
            return self.fallback.user_package_permissions(username)
        return []

    def group_package_permissions(self, group):
        if self.fallback is not None:
            return self.fallback.group_package_permissions(group)
        return []

    def user_data(self, username=None):
        if username is None:
            if self.fallback is not None:
                return self.fallback.user_data()
            return []
        else:
            return {
                "username": username,
                "admin": self.is_admin(username),
                "groups": self.groups(username),
            }

    def check_health(self):
        try:
            self.conn.test_connection()
        except ldap.LDAPError as e:
            return (False, str(e))
        else:
            return (True, "")
