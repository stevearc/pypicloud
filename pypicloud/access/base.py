""" The access backend object base class """
import hashlib
import hmac
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from passlib.apps import LazyCryptContext
from passlib.utils import sys_bits
from pyramid.security import (
    ALL_PERMISSIONS,
    Allow,
    Authenticated,
    Deny,
    Everyone,
    effective_principals,
)
from pyramid.settings import aslist

# Roughly tuned using https://bitbucket.org/ecollins/passlib/raw/default/choose_rounds.py
# For 10ms. This differs from the passlib recommendation of 350ms due to the difference in use case
DEFAULT_ROUNDS = {
    "sha512_crypt__default_rounds": 20500,
    "sha256_crypt__default_rounds": 16000,
    "pbkdf2_sha512__default_rounds": 10500,
    "pbkdf2_sha256__default_rounds": 13000,
    "bcrypt__default_rounds": 7,
    "argon2__default_rounds": 1,
}
SCHEMES = [
    "sha512_crypt",
    "sha256_crypt",
    "pbkdf2_sha512",
    "pbkdf2_sha256",
    "bcrypt",
    "argon2",
]
if sys_bits < 64:
    SCHEMES.remove("sha512_crypt")
    SCHEMES.remove("pbkdf2_sha512")


def get_pwd_context(
    preferred_hash: Optional[str] = None, rounds: Optional[int] = None
) -> LazyCryptContext:
    """ Create a passlib context for hashing passwords """
    if preferred_hash is None or preferred_hash == "sha":
        preferred_hash = "sha256_crypt" if sys_bits < 64 else "sha512_crypt"
    if preferred_hash == "pbkdf2":
        preferred_hash = "pbkdf2_sha256" if sys_bits < 64 else "pbkdf2_sha512"

    if preferred_hash not in SCHEMES:
        raise Exception(
            "Password hash %r is not in the list of supported schemes" % preferred_hash
        )

    # Put the preferred hash at the beginning of the schemes list
    schemes = list(SCHEMES)
    schemes.remove(preferred_hash)
    schemes.insert(0, preferred_hash)

    # Override the default rounds of the preferred hash, if provided
    default_rounds = dict(DEFAULT_ROUNDS)
    if rounds is not None:
        default_rounds[preferred_hash + "__default_rounds"] = rounds

    return LazyCryptContext(schemes=schemes, default=schemes[0], **default_rounds)


def group_to_principal(group: str) -> str:
    """ Convert a group to its corresponding principal """
    if group in (Everyone, Authenticated) or group.startswith("group:"):
        return group
    elif group == "everyone":
        return Everyone
    elif group == "authenticated":
        return Authenticated
    else:
        return "group:" + group


def groups_to_principals(groups: List[str]) -> List[str]:
    """ Convert a list of groups to a list of principals """
    return [group_to_principal(g) for g in groups]


ONE_WEEK = 60 * 60 * 24 * 7


class IAccessBackend(object):

    """ Base class for retrieving user and package permission data """

    mutable = False
    ROOT_ACL = [
        (Allow, Authenticated, "login"),
        (Allow, "admin", ALL_PERMISSIONS),
        (Deny, Everyone, ALL_PERMISSIONS),
    ]

    def __init__(
        self,
        request=None,
        default_read=None,
        default_write=None,
        disallow_fallback=(),
        cache_update=None,
        pwd_context=None,
        token_expiration=ONE_WEEK,
        signing_key=None,
    ):
        self.request = request
        self.default_read = default_read
        self.default_write = default_write
        self.disallow_fallback = disallow_fallback
        self.cache_update = cache_update
        self.pwd_context = pwd_context
        self.token_expiration = token_expiration
        self.signing_key = signing_key

    @classmethod
    def configure(cls, settings) -> Dict[str, Any]:
        """ Configure the access backend with app settings """
        rounds = settings.get("auth.rounds")
        scheme = settings.get("auth.scheme")
        return {
            "default_read": aslist(
                settings.get("pypi.default_read", ["authenticated"])
            ),
            "default_write": aslist(settings.get("pypi.default_write", [])),
            "disallow_fallback": aslist(settings.get("pypi.disallow_fallback", [])),
            "cache_update": aslist(
                settings.get("pypi.cache_update", ["authenticated"])
            ),
            "pwd_context": get_pwd_context(scheme, rounds),
            "token_expiration": int(settings.get("auth.token_expire", ONE_WEEK)),
            "signing_key": settings.get("auth.signing_key"),
        }

    @classmethod
    def postfork(cls, **kwargs):
        """ This method will be called after uWSGI forks """

    def allowed_permissions(self, package: str) -> Dict[str, Tuple[str, ...]]:
        """
        Get all allowed permissions for all principals on a package

        Returns
        -------
        perms : dict
            Mapping of principal to tuple of permissions

        """
        all_perms = {}
        for user, perms in self.user_permissions(package).items():
            all_perms["user:" + user] = tuple(perms)

        for group, perms in self.group_permissions(package).items():
            all_perms[group_to_principal(group)] = tuple(perms)

        # If there are no group or user specifications for the package, use the
        # default
        if not all_perms:
            for principal in groups_to_principals(self.default_read):
                all_perms[principal] = ("read",)
            for principal in groups_to_principals(self.default_write):
                if principal in all_perms:
                    all_perms[principal] += ("write",)
                else:
                    all_perms[principal] = ("write",)

        # add fallback permissions
        if package not in self.disallow_fallback:
            for principal in all_perms:
                all_perms[principal] += ("fallback",)
        return all_perms

    def get_acl(self, package: str) -> List[Tuple[str, str, str]]:
        """ Construct an ACL for a package """
        acl = []
        permissions = self.allowed_permissions(package)
        for principal, perms in permissions.items():
            for perm in perms:
                acl.append((Allow, principal, perm))
        return acl

    def has_permission(self, package: str, perm: str) -> bool:
        """ Check if this user has a permission for a package """
        current_userid = self.request.userid
        if current_userid is not None and self.is_admin(current_userid):
            return True

        perms = self.allowed_permissions(package)
        for principal in effective_principals(self.request):
            if perm in perms.get(principal, []):
                return True
        return False

    def user_principals(self, username: str) -> List[str]:
        """
        Get a list of principals for a user

        Parameters
        ----------
        username : str

        Returns
        -------
        principals : list

        """
        principals = ["user:" + username, Everyone, Authenticated]
        if self.is_admin(username):
            principals.append("admin")
        for group in self.groups(username):
            principals.append("group:" + group)
        return principals

    def in_group(self, username: str, group: str) -> bool:
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
        if group in ("everyone", Everyone):
            return True
        elif username is None:
            return False
        elif group in ("authenticated", Authenticated):
            return True
        elif group == "admin" and self.is_admin(username):
            return True
        else:
            return group in self.groups(username)

    def in_any_group(self, username: str, groups: List[str]) -> bool:
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

    def can_update_cache(self) -> bool:
        """
        Return True if the user has permissions to update the pypi cache
        """
        return self.in_any_group(self.request.userid, self.cache_update)

    def need_admin(self) -> bool:
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

    def allow_register(self) -> bool:
        """
        Check if the backend allows registration

        This should only be overridden by mutable backends

        Returns
        -------
        allow : bool

        """
        return False

    def allow_register_token(self) -> bool:
        """
        Check if the backend allows registration via tokens

        This should only be overridden by mutable backends

        Returns
        -------
        allow : bool

        """
        return False

    def verify_user(self, username: str, password: str) -> bool:
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
        return bool(stored_pw and self.pwd_context.verify(password, stored_pw))

    def _get_password_hash(self, username: str) -> str:
        """ Get the stored password hash for a user """
        raise NotImplementedError

    def groups(self, username: Optional[str] = None) -> List[str]:
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

    def group_members(self, group: str) -> List[str]:
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

    def is_admin(self, username: str) -> bool:
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

    def group_permissions(self, package: str) -> Dict[str, List[str]]:
        """
        Get a mapping of all groups to their permissions on a package

        Parameters
        ----------
        package : str
            The name of a python package


        Returns
        -------
        permissions : dict
            mapping of group name to a list of permissions
            (which can contain 'read' and/or 'write')

        """
        raise NotImplementedError

    def user_permissions(self, package: str) -> Dict[str, List[str]]:
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

    def user_package_permissions(self, username: str) -> List[Dict[str, List[str]]]:
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

    def group_package_permissions(self, group: str) -> List[Dict[str, List[str]]]:
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

    def check_health(self) -> Tuple[bool, str]:
        """
        Check the health of the access backend

        Returns
        -------
        (healthy, status) : (bool, str)
            Tuple that describes the health status and provides an optional
            status message

        """
        return True, ""

    def dump(self) -> Dict[str, Any]:
        """
        Dump all of the access control data to a universal format

        Returns
        -------
        data : dict

        """
        from pypicloud import __version__

        data = {}  # type: Dict[str, Any]
        data["allow_register"] = self.allow_register()
        data["version"] = __version__

        groups = self.groups()
        users = self.user_data()
        for user in users:
            user["password"] = self._get_password_hash(user["username"])

        data["groups"] = {}
        packages = {
            "users": defaultdict(dict),
            "groups": defaultdict(dict),
        }  # type: Dict[str, Any]
        for group in groups:
            data["groups"][group] = self.group_members(group)
            perms = self.group_package_permissions(group)
            for perm in perms:
                package = perm["package"]
                packages["groups"][package][group] = perm["permissions"]

        for user in users:
            username = user["username"]
            perms = self.user_package_permissions(username)
            for perm in perms:
                package = perm["package"]
                packages["users"][package][username] = perm["permissions"]

        # Convert the defaultdict to a dict for easy serialization
        packages["users"] = dict(packages["users"])
        packages["groups"] = dict(packages["groups"])
        data["users"] = users
        data["packages"] = packages
        return data

    def load(self, data):
        """
        Idempotently load universal access control data.

        By default, this does nothing on immutable backends. Backends may
        override this method to provide an implementation.

        This method works by default on mutable backends with no override
        necessary.

        """
        raise TypeError(
            "Access backend '%s' is not mutable and has no "
            "'load' implementation" % self.__class__.__name__
        )


class IMutableAccessBackend(IAccessBackend):

    """
    Base class for access backends that can change user/group permissions

    """

    mutable = True

    def need_admin(self) -> bool:
        for user in self.user_data():
            if user["admin"]:
                return False
        return True

    def get_signup_token(self, username: str) -> str:
        """
        Create a signup token

        Parameters
        ----------
        username : str
            The username to be created when this token is consumed

        Returns
        -------
        token : str

        """
        msg, signature = self._hmac(username, time.time())
        return msg + ":" + signature

    def _hmac(self, username: str, timestamp: float) -> Tuple[str, str]:
        """ HMAC a username/expiration combo """
        if self.signing_key is None:
            raise RuntimeError("auth.signing_key is not set!")
        msg = "%s:%d" % (username, timestamp)
        return (
            msg,
            hmac.new(
                self.signing_key.encode("utf8"), msg.encode("utf8"), hashlib.sha256
            ).hexdigest(),
        )

    def validate_signup_token(self, token: str) -> Optional[str]:
        """
        Validate a signup token

        Parameters
        ----------
        token : str

        Returns
        -------
        username : str or None
            This will be None if the validation fails

        """
        if self.signing_key is None:
            return None
        pieces = token.split(":")
        signature = pieces.pop()
        username = pieces[0]
        issued = int(pieces[1])
        if issued + self.token_expiration < time.time():
            return None
        _, expected = self._hmac(username, issued)
        if hasattr(hmac, "compare_digest"):
            if not hmac.compare_digest(
                signature.encode("utf-8"), expected.encode("utf-8")
            ):
                return None
        else:
            if signature != expected:
                return None
        return username

    def allow_register(self):
        raise NotImplementedError

    def allow_register_token(self):
        return self.signing_key is not None

    def set_allow_register(self, allow: bool) -> None:
        """
        Allow or disallow user registration

        Parameters
        ----------
        allow : bool

        """
        raise NotImplementedError

    def register(self, username: str, password: str) -> None:
        """
        Register a new user

        The new user should be marked as pending admin approval

        Parameters
        ----------
        username : str
        password : str
            This should be the plaintext password

        """
        self._register(username, self.pwd_context.hash(password))

    def _register(self, username: str, password: str) -> None:
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

    def pending_users(self) -> List[str]:
        """
        Retrieve a list of all users pending admin approval

        Returns
        -------
        users : list
            List of usernames

        """
        raise NotImplementedError

    def approve_user(self, username: str) -> None:
        """
        Mark a user as approved by the admin

        Parameters
        ----------
        username : str

        """
        raise NotImplementedError

    def edit_user_password(self, username: str, password: str) -> None:
        """
        Change a user's password

        Parameters
        ----------
        username : str
        password : str

        """
        self._set_password_hash(username, self.pwd_context.hash(password))

    def _set_password_hash(self, username: str, password_hash: str) -> None:
        """
        Change a user's password

        Parameters
        ----------
        username : str
        password_hash : str
            The hashed password to store

        """
        raise NotImplementedError

    def delete_user(self, username: str) -> None:
        """
        Delete a user

        Parameters
        ----------
        username : str

        """
        raise NotImplementedError

    def set_user_admin(self, username: str, admin: bool) -> None:
        """
        Grant or revoke admin permissions for a user

        Parameters
        ----------
        username : str
        admin : bool
            If True, grant permissions. If False, revoke.

        """
        raise NotImplementedError

    def edit_user_group(self, username: str, group: str, add: bool) -> None:
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

    def create_group(self, group: str) -> None:
        """
        Create a new group

        Parameters
        ----------
        group : str

        """
        raise NotImplementedError

    def delete_group(self, group: str) -> None:
        """
        Delete a group

        Parameters
        ----------
        group : str

        """
        raise NotImplementedError

    def edit_user_permission(
        self, package: str, username: str, perm: Set[str], add: bool
    ) -> None:
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

    def edit_group_permission(
        self, package: str, group: str, perm: Set[str], add: bool
    ) -> None:
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
            pending_users.append({"username": username, "password": password})
        data["pending_users"] = pending_users
        return data

    def load(self, data):
        pending_users = set(self.pending_users())

        def user_exists(username):
            """ Helper function that checks if a user already exists """
            return username in pending_users or self.user_data(username) is not None

        for user in data["users"]:
            if not user_exists(user["username"]):
                self._register(user["username"], user["password"])
                self.approve_user(user["username"])
            self.set_user_admin(user["username"], user.get("admin", False))

        for group, members in data["groups"].items():
            if not self.group_members(group):
                self.create_group(group)
            current_members = self.group_members(group)
            add_members = set(members) - set(current_members)
            for member in add_members:
                self.edit_user_group(member, group, True)

        for user in data.get("pending_users", []):
            if not user_exists(user["username"]):
                self._register(user["username"], user["password"])

        for package, groups in data["packages"]["groups"].items():
            for group, permissions in groups.items():
                for perm in permissions:
                    self.edit_group_permission(package, group, perm, True)

        for package, users in data["packages"]["users"].items():
            for user, permissions in users.items():
                for perm in permissions:
                    self.edit_user_permission(package, user, perm, True)

        self.set_allow_register(data["allow_register"])
