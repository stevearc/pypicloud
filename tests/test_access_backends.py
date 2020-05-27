# -*- coding: utf-8 -*-
""" Tests for access backends """
import json
import unittest

import transaction
import zope.sqlalchemy
from mock import MagicMock, patch
from mockldap import MockLdap
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.security import Authenticated, Everyone
from pyramid.testing import DummyRequest
from sqlalchemy.exc import OperationalError, SQLAlchemyError

import ldap
from pypicloud.access import (
    ConfigAccessBackend,
    IAccessBackend,
    IMutableAccessBackend,
    RemoteAccessBackend,
    aws_secrets_manager,
    get_pwd_context,
    includeme,
)
from pypicloud.access.base import group_to_principal
from pypicloud.access.ldap_ import LDAPAccessBackend
from pypicloud.access.sql import (
    Base,
    Group,
    GroupPermission,
    SQLAccessBackend,
    User,
    UserPermission,
    association_table,
)
from pypicloud.route import Root

pwd_context = get_pwd_context()  # pylint: disable=C0103


class PartialEq(object):

    """ Helper object to compare equality against functools.partial objects """

    def __init__(self, obj):
        self.obj = obj

    def __eq__(self, other):
        return self.obj == other.func

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return "partial(%s)" % self.obj


def make_user(name, password, pending=True):
    """ Convenience method for creating a User """
    return User(name, pwd_context.hash(password), pending)


class TestUtilities(unittest.TestCase):

    """ Tests for the access utilities """

    def test_group_to_principal(self):
        """ group_to_principal formats groups """
        self.assertEqual(group_to_principal("foo"), "group:foo")
        self.assertEqual(group_to_principal("everyone"), Everyone)
        self.assertEqual(group_to_principal("authenticated"), Authenticated)

    def test_group_to_principal_twice(self):
        """ Running group_to_principal twice has no effect """
        for group in ("foo", "everyone", "authenticated"):
            g1 = group_to_principal(group)
            g2 = group_to_principal(g1)
            self.assertEqual(g1, g2)


class BaseACLTest(unittest.TestCase):

    """ Base test for anything checking ACLs """

    def setUp(self):
        self.request = DummyRequest()
        self.request.userid = None
        self.auth = ACLAuthorizationPolicy()

    def allowed(self, context, perm):
        """ Get all allowed principals from a context or an ACL """
        if not hasattr(context, "__acl__"):
            acl = context
            context = MagicMock()
            context.__acl__ = acl
            context.__parent__ = None
        return self.auth.principals_allowed_by_permission(context, perm)

    def assert_allowed(self, context, perm, principals):
        """ Assert that only a particular set of principals has access """
        allowed = self.allowed(context, perm)
        self.assertEqual(allowed, set(principals))


class TestBaseBackend(BaseACLTest):

    """ Tests for the access backend interface """

    def setUp(self):
        super(TestBaseBackend, self).setUp()
        self.backend = IAccessBackend(self.request)
        patch.object(self.backend, "verify_user").start()
        patch.object(self.backend, "groups").start()
        patch.object(self.backend, "is_admin").start()
        patch.object(self.backend, "group_permissions").start()
        patch.object(self.backend, "user_permissions").start()
        self.request.access = self.backend

    def tearDown(self):
        super(TestBaseBackend, self).tearDown()
        patch.stopall()

    def test_root_acl(self):
        """ Root ACL sets login, admin, and DENY ALL """
        root = Root(self.request)
        self.assert_allowed(root, "login", ["admin", Authenticated])
        self.assert_allowed(root, "admin", ["admin"])
        self.assert_allowed(root, "arbitrary", ["admin"])

    def test_user_rw(self):
        """ Owner always has rw perms on a package """
        self.backend.user_permissions.return_value = {"dsa": ["read", "write"]}
        acl = self.backend.get_acl("mypkg")
        self.assert_allowed(acl, "read", ["user:dsa"])
        self.assert_allowed(acl, "write", ["user:dsa"])

    def test_group_everyone(self):
        """ Special 'everyone' group sets perms for everyone """
        self.backend.group_permissions.return_value = {"everyone": ["read", "write"]}
        acl = self.backend.get_acl("mypkg")
        self.assert_allowed(acl, "read", [Everyone])
        self.assert_allowed(acl, "write", [Everyone])

    def test_group_authenticated(self):
        """ Special 'authenticated' group sets perms for logged-in users """
        self.backend.group_permissions.return_value = {
            "authenticated": ["read", "write"]
        }
        acl = self.backend.get_acl("mypkg")
        self.assert_allowed(acl, "read", [Authenticated])
        self.assert_allowed(acl, "write", [Authenticated])

    def test_group(self):
        """ Groups set perms for a 'group:<>' principal """
        self.backend.group_permissions.return_value = {"brotatos": ["read", "write"]}
        acl = self.backend.get_acl("mypkg")
        self.assert_allowed(acl, "read", ["group:brotatos"])
        self.assert_allowed(acl, "write", ["group:brotatos"])

    def test_abstract_methods(self):
        """ Abstract methods raise NotImplementedError """
        access = IMutableAccessBackend(None, pwd_context=get_pwd_context())
        with self.assertRaises(NotImplementedError):
            access.verify_user("a", "b")
        with self.assertRaises(NotImplementedError):
            access.groups()
        with self.assertRaises(NotImplementedError):
            access.group_members("a")
        with self.assertRaises(NotImplementedError):
            access.is_admin("a")
        with self.assertRaises(NotImplementedError):
            access.group_permissions("a")
        with self.assertRaises(NotImplementedError):
            access.user_permissions("a")
        with self.assertRaises(NotImplementedError):
            access.user_package_permissions("a")
        with self.assertRaises(NotImplementedError):
            access.group_package_permissions("a")
        with self.assertRaises(NotImplementedError):
            access.user_data()
        with self.assertRaises(NotImplementedError):
            access.allow_register()
        with self.assertRaises(NotImplementedError):
            access.set_allow_register(True)
        with self.assertRaises(NotImplementedError):
            access.register("a", "b")
        with self.assertRaises(NotImplementedError):
            access.pending_users()
        with self.assertRaises(NotImplementedError):
            access.approve_user("a")
        with self.assertRaises(NotImplementedError):
            access.edit_user_password("a", "b")
        with self.assertRaises(NotImplementedError):
            access.delete_user("a")
        with self.assertRaises(NotImplementedError):
            access.set_user_admin("a", True)
        with self.assertRaises(NotImplementedError):
            access.edit_user_group("a", "a", "add")
        with self.assertRaises(NotImplementedError):
            access.create_group("a")
        with self.assertRaises(NotImplementedError):
            access.delete_group("a")
        with self.assertRaises(NotImplementedError):
            access.edit_user_permission("a", "b", "c", True)
        with self.assertRaises(NotImplementedError):
            access.edit_group_permission("a", "b", "c", True)

    def test_need_admin(self):
        """ need_admin is True if no admins """
        access = IMutableAccessBackend(None)
        with patch.object(access, "user_data") as user_data:
            user_data.return_value = [{"admin": False}]
            self.assertTrue(access.need_admin())

    def test_no_need_admin(self):
        """ need_admin is False if 1+ admins """
        access = IMutableAccessBackend(None)
        with patch.object(access, "user_data") as user_data:
            user_data.return_value = [{"admin": False}, {"admin": True}]
            self.assertFalse(access.need_admin())

    def test_load_remote_backend(self):
        """ keyword 'remote' loads RemoteBackend """
        config = MagicMock()
        config.get_settings.return_value = {
            "pypi.auth": "remote",
            "auth.backend_server": "http://example.com",
        }
        includeme(config)
        config.add_request_method.assert_called_with(
            PartialEq(RemoteAccessBackend), name="access", reify=True
        )

    def test_load_sql_backend(self):
        """ keyword 'sql' loads SQLBackend """
        config = MagicMock()
        config.get_settings.return_value = {
            "auth.db.url": "sqlite://",
            "pypi.auth": "sql",
        }
        includeme(config)
        config.add_request_method.assert_called_with(
            PartialEq(SQLAccessBackend), name="access", reify=True
        )

    def test_load_arbitrary_backend(self):
        """ Can pass dotted path to load arbirary backend """
        config = MagicMock()
        config.get_settings.return_value = {
            "auth.db.url": "sqlite://",
            "pypi.auth": "pypicloud.access.sql.SQLAccessBackend",
        }
        includeme(config)
        config.add_request_method.assert_called_with(
            PartialEq(SQLAccessBackend), name="access", reify=True
        )

    def test_admin_has_permission(self):
        """ Admins always have permission """
        self.request.userid = "abc"
        access = IAccessBackend(self.request)
        access.is_admin = lambda x: True
        self.assertTrue(access.has_permission("p1", "write"))

    def test_has_permission_default_read(self):
        """ If no user/group permissions on a package, use default_read """
        self.backend.default_read = ["everyone", "authenticated"]
        self.backend.default_write = []
        perms = self.backend.allowed_permissions("anypkg")
        self.assertEqual(
            perms, {Everyone: ("read", "fallback"), Authenticated: ("read", "fallback")}
        )

    def test_has_permission_default_write(self):
        """ If no user/group permissions on a package, use default_write """
        self.backend.default_read = ["authenticated"]
        self.backend.default_write = ["authenticated"]
        perms = self.backend.allowed_permissions("anypkg")
        self.assertEqual(perms, {Authenticated: ("read", "write", "fallback")})

    def test_admin_principal(self):
        """ Admin user has the 'admin' principal """
        access = IAccessBackend(None)
        access.is_admin = lambda x: True
        with patch.object(access, "groups") as groups:
            groups.return_value = ["brotatos"]
            principals = access.user_principals("abc")
        self.assertItemsEqual(
            principals, [Everyone, Authenticated, "admin", "group:brotatos", "user:abc"]
        )

    def test_load(self):
        """ Base backend has no default implementation for load() """
        access = IAccessBackend(None)
        with self.assertRaises(TypeError):
            access.load({})

    def test_hmac_validate(self):
        """ hmac will validate """
        access = IMutableAccessBackend(signing_key="abc")
        user = "foobar"
        token = access.get_signup_token(user)
        self.assertEqual(user, access.validate_signup_token(token))

    def test_hmac_expire(self):
        """ hmac will expire after a time """
        access = IMutableAccessBackend(signing_key="abc", token_expiration=-10)
        user = "foobar"
        token = access.get_signup_token(user)
        self.assertIsNone(access.validate_signup_token(token))

    def test_hmac_invalid(self):
        """ hmac will be invalid if mutated """
        access = IMutableAccessBackend(signing_key="abc")
        user = "foobar"
        token = access.get_signup_token(user)
        self.assertIsNone(access.validate_signup_token(token + "a"))

    def test_check_health(self):
        """ Base check_health returns True """
        ok, msg = self.backend.check_health()
        self.assertTrue(ok)


class TestConfigBackend(BaseACLTest):

    """ Tests for access backend that uses config settings """

    def _backend(self, settings):
        """ Wrapper to instantiate a ConfigAccessBackend """
        kwargs = ConfigAccessBackend.configure(settings)
        request = DummyRequest()
        request.userid = None
        return ConfigAccessBackend(request, **kwargs)

    def test_build_group(self):
        """ Group specifications create user map to groups """
        settings = {
            "group.g1": "u1 u2 u3",
            "group.g2": "u2 u3 u4",
            "unrelated": "weeeeee",
        }
        backend = self._backend(settings)
        self.assertItemsEqual(backend.groups(), ["g1", "g2"])
        self.assertItemsEqual(backend.groups("u1"), ["g1"])
        self.assertItemsEqual(backend.groups("u2"), ["g1", "g2"])
        self.assertItemsEqual(backend.groups("u3"), ["g1", "g2"])
        self.assertItemsEqual(backend.groups("u4"), ["g2"])

    def test_verify(self):
        """ Users can log in with correct password """
        settings = {"user.u1": pwd_context.hash("foobar")}
        backend = self._backend(settings)
        valid = backend.verify_user("u1", "foobar")
        self.assertTrue(valid)

    def test_no_verify(self):
        """ Verification fails with wrong password """
        settings = {"user.u1": pwd_context.hash("foobar")}
        backend = self._backend(settings)
        valid = backend.verify_user("u1", "foobarz")
        self.assertFalse(valid)

    def test_group_members(self):
        """ Fetch all members of a group """
        settings = {"group.g1": "u1 u2 u3"}
        backend = self._backend(settings)
        self.assertItemsEqual(backend.group_members("g1"), ["u1", "u2", "u3"])

    def test_all_group_permissions(self):
        """ Fetch all group permissions on a package """
        settings = {"package.mypkg.group.g1": "r", "package.mypkg.group.g2": "rw"}
        backend = self._backend(settings)
        perms = backend.group_permissions("mypkg")
        self.assertEqual(perms, {"g1": ["read"], "g2": ["read", "write"]})

    @patch("pypicloud.access.base.effective_principals")
    def test_everyone_permission(self, principals):
        """ All users have 'everyone' permissions """
        settings = {"package.mypkg.group.everyone": "r"}
        principals.return_value = [Everyone]
        backend = self._backend(settings)
        self.assertTrue(backend.has_permission("mypkg", "read"))
        self.assertFalse(backend.has_permission("mypkg", "write"))

    @patch("pypicloud.access.base.effective_principals")
    def test_authenticated_permission(self, principals):
        """ All logged-in users have 'authenticated' permissions """
        settings = {"package.mypkg.group.authenticated": "r"}
        principals.return_value = [Authenticated]
        backend = self._backend(settings)
        self.assertTrue(backend.has_permission("mypkg", "read"))
        self.assertFalse(backend.has_permission("mypkg", "write"))

    def test_all_user_perms(self):
        """ Fetch permissions on a package for all users """
        settings = {"package.mypkg.user.u1": "r", "package.mypkg.user.u2": "rw"}
        backend = self._backend(settings)
        perms = backend.user_permissions("mypkg")
        self.assertEqual(perms, {"u1": ["read"], "u2": ["read", "write"]})

    def test_user_package_perms(self):
        """ Fetch all packages a user has permissions on """
        settings = {
            "package.pkg1.user.u1": "r",
            "package.pkg2.user.u1": "rw",
            "unrelated.field": "",
        }
        backend = self._backend(settings)
        packages = backend.user_package_permissions("u1")
        self.assertItemsEqual(
            packages,
            [
                {"package": "pkg1", "permissions": ["read"]},
                {"package": "pkg2", "permissions": ["read", "write"]},
            ],
        )

    def test_long_user_package_perms(self):
        """ Can encode user package permissions in verbose form """
        settings = {
            "package.pkg1.user.u1": "read ",
            "package.pkg2.user.u1": "read write",
            "unrelated.field": "",
        }
        backend = self._backend(settings)
        packages = backend.user_package_permissions("u1")
        self.assertItemsEqual(
            packages,
            [
                {"package": "pkg1", "permissions": ["read"]},
                {"package": "pkg2", "permissions": ["read", "write"]},
            ],
        )

    def test_group_package_perms(self):
        """ Fetch all packages a group has permissions on """
        settings = {
            "package.pkg1.group.g1": "r",
            "package.pkg2.group.g1": "rw",
            "unrelated.field": "",
        }
        backend = self._backend(settings)
        packages = backend.group_package_permissions("g1")
        self.assertItemsEqual(
            packages,
            [
                {"package": "pkg1", "permissions": ["read"]},
                {"package": "pkg2", "permissions": ["read", "write"]},
            ],
        )

    def test_user_data(self):
        """ Retrieve all users """
        settings = {"user.foo": "pass", "user.bar": "pass", "auth.admins": ["foo"]}
        backend = self._backend(settings)
        users = backend.user_data()
        self.assertItemsEqual(
            users,
            [{"username": "foo", "admin": True}, {"username": "bar", "admin": False}],
        )

    def test_single_user_data(self):
        """ Get data for a single user """
        settings = {
            "user.foo": "pass",
            "auth.admins": ["foo"],
            "group.foobars": ["foo"],
        }
        backend = self._backend(settings)
        user = backend.user_data("foo")
        self.assertEqual(
            user, {"username": "foo", "admin": True, "groups": ["foobars"]}
        )

    def test_need_admin(self):
        """ Config backend is static and never needs admin """
        backend = self._backend({})
        self.assertFalse(backend.need_admin())

    def test_load(self):
        """ Config backend can load ACL and format config strings """
        settings = {
            "group.g1": "u1 u3",
            "user.u1": "passhash",
            "user.u2": "hashpass",
            "user.u3": "hashhhhh",
            "auth.admins": "u1 u2",
            "package.pkg.user.u1": "rw",
            "package.pkg.group.g1": "r",
        }
        backend = self._backend(settings)
        data = backend.dump()
        config = backend.load(data)

        def parse_config(string):
            """ Parse the settings from config.ini format """
            conf = {}
            key, value = None, None
            for line in string.splitlines():
                if line.startswith(" "):
                    value += " " + line.strip()
                else:
                    if key is not None:
                        conf[key] = " ".join(sorted(value.split())).strip()
                    key, value = line.split("=")
                    key = key.strip()
                    value = value.strip()
            conf[key] = " ".join(sorted(value.split())).strip()
            return conf

        self.assertEqual(parse_config(config), settings)


class TestRemoteBackend(unittest.TestCase):

    """ Tests for the access backend that delegates calls to remote server """

    def setUp(self):
        request = DummyRequest()
        self.auth = ("user", "pass")
        settings = {
            "auth.backend_server": "server",
            "auth.user": self.auth[0],
            "auth.password": self.auth[1],
        }
        kwargs = RemoteAccessBackend.configure(settings)
        self.backend = RemoteAccessBackend(request, **kwargs)
        self.requests = MagicMock()
        patch.dict("sys.modules", requests=self.requests).start()

    def tearDown(self):
        patch.stopall()

    def test_verify(self):
        """ Delegate login to remote server """
        verified = self.backend.verify_user("user", "pass")
        params = {"username": "user", "password": "pass"}
        self.requests.get.assert_called_with(
            "server/verify", params=params, auth=self.auth
        )
        self.assertEqual(verified, self.requests.get().json())

    def test_user_groups(self):
        """ Delegate fetching user groups to remote server """
        groups = self.backend.groups("dsa")
        params = {"username": "dsa"}
        self.requests.get.assert_called_with(
            "server/groups", params=params, auth=self.auth
        )
        self.assertEqual(groups, self.requests.get().json())

    def test_all_groups(self):
        """ Delegate fetching all groups to remote server """
        groups = self.backend.groups()
        self.requests.get.assert_called_with("server/groups", params={}, auth=self.auth)
        self.assertEqual(groups, self.requests.get().json())

    def test_group_members(self):
        """ Delegate fetching group members to remote server """
        groups = self.backend.group_members("g1")
        params = {"group": "g1"}
        self.requests.get.assert_called_with(
            "server/group_members", params=params, auth=self.auth
        )
        self.assertEqual(groups, self.requests.get().json())

    def test_admin(self):
        """ Query server to determine if user is admin """
        is_admin = self.backend.is_admin("dsa")
        params = {"username": "dsa"}
        self.requests.get.assert_called_with(
            "server/admin", params=params, auth=self.auth
        )
        self.assertEqual(is_admin, self.requests.get().json())

    def test_all_group_perms(self):
        """ Query server for all group permissions on a package """
        perms = self.backend.group_permissions("mypkg")
        params = {"package": "mypkg"}
        self.requests.get.assert_called_with(
            "server/group_permissions", params=params, auth=self.auth
        )
        self.assertEqual(perms, self.requests.get().json())

    def test_all_user_perms(self):
        """ Query server for all user permissions on a package """
        perms = self.backend.user_permissions("mypkg")
        params = {"package": "mypkg"}
        self.requests.get.assert_called_with(
            "server/user_permissions", params=params, auth=self.auth
        )
        self.assertEqual(perms, self.requests.get().json())

    def test_user_data(self):
        """ Retrieve all users """
        users = self.backend.user_data()
        self.requests.get.assert_called_with(
            "server/user_data", params=None, auth=self.auth
        )
        self.assertEqual(users, self.requests.get().json())

    def test_single_user_data(self):
        """ Retrieve user data """
        users = self.backend.user_data("foo")
        self.requests.get.assert_called_with(
            "server/user_data", params={"username": "foo"}, auth=self.auth
        )
        self.assertEqual(users, self.requests.get().json())

    def test_user_package_perms(self):
        """ Fetch all packages a user has permissions on """
        users = self.backend.user_package_permissions("u1")
        params = {"username": "u1"}
        self.requests.get.assert_called_with(
            "server/user_package_permissions", params=params, auth=self.auth
        )
        self.assertEqual(users, self.requests.get().json())

    def test_group_package_perms(self):
        """ Fetch all packages a group has permissions on """
        groups = self.backend.group_package_permissions("g1")
        params = {"group": "g1"}
        self.requests.get.assert_called_with(
            "server/group_package_permissions", params=params, auth=self.auth
        )
        self.assertEqual(groups, self.requests.get().json())


class TestSQLiteBackend(unittest.TestCase):
    """ Tests for the SQL access backend """

    DB_URL = "sqlite://"

    @classmethod
    def setUpClass(cls):
        super(TestSQLiteBackend, cls).setUpClass()
        cls.settings = {"auth.db.url": cls.DB_URL}
        try:
            cls.kwargs = SQLAccessBackend.configure(cls.settings)
        except OperationalError:
            raise unittest.SkipTest("Couldn't connect to database")

    def setUp(self):
        super(TestSQLiteBackend, self).setUp()
        transaction.begin()
        request = MagicMock()
        request.tm = transaction.manager
        self.access = SQLAccessBackend(request, **self.kwargs)
        self.db = self.kwargs["dbmaker"]()
        zope.sqlalchemy.register(self.db, transaction_manager=transaction.manager)

    def tearDown(self):
        super(TestSQLiteBackend, self).tearDown()
        transaction.abort()
        self.access.db.close()
        self.db.close()
        self._drop_and_recreate()

    def _drop_and_recreate(self):
        """ Drop all tables and recreate them """
        Base.metadata.drop_all(bind=self.db.get_bind())
        Base.metadata.create_all(bind=self.db.get_bind())

    def test_verify(self):
        """ Verify login credentials against database """
        user = make_user("foo", "bar", False)
        self.db.add(user)
        transaction.commit()
        valid = self.access.verify_user("foo", "bar")
        self.assertTrue(valid)

        valid = self.access.verify_user("foo", "barrrr")
        self.assertFalse(valid)

    def test_verify_pending(self):
        """ Pending users fail to verify """
        user = make_user("foo", "bar")
        self.db.add(user)
        transaction.commit()
        valid = self.access.verify_user("foo", "bar")
        self.assertFalse(valid)

    def test_admin(self):
        """ Retrieve admin status from database """
        user = make_user("foo", "bar", False)
        user.admin = True
        self.db.add(user)
        transaction.commit()
        is_admin = self.access.is_admin("foo")
        self.assertTrue(is_admin)

    def test_admin_default_false(self):
        """ The default admin status is False """
        user = make_user("foo", "bar", False)
        self.db.add(user)
        transaction.commit()
        is_admin = self.access.is_admin("foo")
        self.assertFalse(is_admin)

    def test_user_groups(self):
        """ Retrieve a user's groups from database """
        user = make_user("foo", "bar", False)
        g1 = Group("brotatos")
        g2 = Group("sharkfest")
        user.groups.update([g1, g2])
        self.db.add_all([user, g1, g2])
        transaction.commit()
        groups = self.access.groups("foo")
        self.assertItemsEqual(groups, ["brotatos", "sharkfest"])

    def test_groups(self):
        """ Retrieve all groups from database """
        user = make_user("foo", "bar", False)
        g1 = Group("brotatos")
        g2 = Group("sharkfest")
        user.groups.add(g1)
        user.groups.add(g2)
        self.db.add(user)
        transaction.commit()
        groups = self.access.groups()
        self.assertItemsEqual(groups, ["brotatos", "sharkfest"])

    def test_group_members(self):
        """ Fetch all members of a group """
        u1 = make_user("u1", "bar", False)
        u2 = make_user("u2", "bar", False)
        u3 = make_user("u3", "bar", False)
        g1 = Group("g1")
        g1.users.update([u1, u2])
        self.db.add_all([u1, u2, u3, g1])
        transaction.commit()
        users = self.access.group_members("g1")
        self.assertItemsEqual(users, ["u1", "u2"])

    def test_all_user_permissions(self):
        """ Retrieve all user permissions on package from database """
        user = make_user("foo", "bar", False)
        user2 = make_user("foo2", "bar", False)
        p1 = UserPermission("pkg1", "foo", True, False)
        p2 = UserPermission("pkg1", "foo2", True, True)
        self.db.add_all([user, user2, p1, p2])
        transaction.commit()
        perms = self.access.user_permissions("pkg1")
        self.assertEqual(perms, {"foo": ["read"], "foo2": ["read", "write"]})

    def test_all_group_permissions(self):
        """ Retrieve all group permissions from database """
        g1 = Group("brotatos")
        g2 = Group("sharkfest")
        p1 = GroupPermission("pkg1", "brotatos", True, False)
        p2 = GroupPermission("pkg1", "sharkfest", True, True)
        self.db.add_all([g1, g2, p1, p2])
        transaction.commit()
        perms = self.access.group_permissions("pkg1")
        self.assertEqual(perms, {"brotatos": ["read"], "sharkfest": ["read", "write"]})

    def test_user_package_perms(self):
        """ Fetch all packages a user has permissions on """
        user = make_user("foo", "bar", False)
        p1 = UserPermission("pkg1", "foo", True, False)
        p2 = UserPermission("pkg2", "foo", True, True)
        self.db.add_all([user, p1, p2])
        transaction.commit()
        perms = self.access.user_package_permissions("foo")
        self.assertEqual(
            perms,
            [
                {"package": "pkg1", "permissions": ["read"]},
                {"package": "pkg2", "permissions": ["read", "write"]},
            ],
        )

    def test_group_package_perms(self):
        """ Fetch all packages a group has permissions on """
        g1 = Group("foo")
        p1 = GroupPermission("pkg1", "foo", True, False)
        p2 = GroupPermission("pkg2", "foo", True, True)
        self.db.add_all([g1, p1, p2])
        transaction.commit()
        perms = self.access.group_package_permissions("foo")
        self.assertEqual(
            perms,
            [
                {"package": "pkg1", "permissions": ["read"]},
                {"package": "pkg2", "permissions": ["read", "write"]},
            ],
        )

    def test_user_data(self):
        """ Retrieve all users """
        u1 = make_user("foo", "bar", False)
        u1.admin = True
        u2 = make_user("bar", "bar", False)
        g1 = Group("foobars")
        u2.groups.add(g1)
        self.db.add_all([u1, u2, g1])
        transaction.commit()
        users = self.access.user_data()
        self.assertItemsEqual(
            users,
            [{"username": "foo", "admin": True}, {"username": "bar", "admin": False}],
        )

    def test_single_user_data(self):
        """ Retrieve a single user's data """
        u1 = make_user("foo", "bar", False)
        u1.admin = True
        g1 = Group("foobars")
        u1.groups.add(g1)
        self.db.add_all([u1, g1])
        transaction.commit()
        user = self.access.user_data("foo")
        self.assertEqual(
            user, {"username": "foo", "admin": True, "groups": ["foobars"]}
        )

    def test_no_need_admin(self):
        """ If admin exists, don't need an admin """
        user = make_user("foo", "bar", False)
        user.admin = True
        self.db.add(user)
        transaction.commit()
        self.assertFalse(self.access.need_admin())

    def test_need_admin(self):
        """ If admin doesn't exist, need an admin """
        user = make_user("foo", "bar", False)
        self.db.add(user)
        transaction.commit()
        self.assertTrue(self.access.need_admin())

    # Tests for mutable backend methods

    def test_register(self):
        """ Register a new user """
        self.access.register("foo", "bar")
        transaction.commit()
        user = self.db.query(User).first()
        self.assertEqual(user.username, "foo")
        self.assertTrue(pwd_context.verify("bar", user.password))

    def test_pending(self):
        """ Registering a user puts them in pending list """
        user = make_user("foo", "bar")
        self.db.add(user)
        transaction.commit()
        users = self.access.pending_users()
        self.assertEqual(users, ["foo"])

    def test_pending_not_in_users(self):
        """ Pending users are not listed in all_users """
        user = make_user("foo", "bar")
        self.db.add(user)
        transaction.commit()
        users = self.access.user_data()
        self.assertEqual(users, [])

    def test_approve(self):
        """ Approving user marks them as not pending """
        user = make_user("foo", "bar")
        self.db.add(user)
        transaction.commit()
        self.access.approve_user("foo")
        transaction.commit()
        user = self.db.query(User).first()
        self.assertFalse(user.pending)

    def test_edit_password(self):
        """ Users can edit their passwords """
        user = make_user("foo", "bar", False)
        self.db.add(user)
        transaction.commit()
        self.access.edit_user_password("foo", "baz")
        transaction.commit()
        user = self.db.query(User).first()
        self.assertTrue(self.access.verify_user("foo", "baz"))

    def test_delete_user(self):
        """ Can delete users """
        user = make_user("foo", "bar", False)
        p1 = UserPermission("pkg1", "foo", True, False)
        group = Group("foobar")
        user.groups.add(group)
        self.db.add_all([user, group, p1])
        transaction.commit()
        self.access.delete_user("foo")
        transaction.commit()
        user = self.db.query(User).first()
        self.assertIsNone(user)
        count = self.db.query(association_table).count()
        self.assertEqual(count, 0)

    def test_make_admin(self):
        """ Can make a user an admin """
        user = make_user("foo", "bar", False)
        self.db.add(user)
        transaction.commit()
        self.access.set_user_admin("foo", True)
        transaction.commit()
        self.db.add(user)
        self.assertTrue(user.admin)

    def test_remove_admin(self):
        """ Can demote an admin to normal user """
        user = make_user("foo", "bar", False)
        user.admin = True
        self.db.add(user)
        transaction.commit()
        self.access.set_user_admin("foo", False)
        transaction.commit()
        self.db.add(user)
        self.assertFalse(user.admin)

    def test_add_user_to_group(self):
        """ Can add a user to a group """
        user = make_user("foo", "bar", False)
        group = Group("g1")
        self.db.add_all([user, group])
        transaction.commit()
        self.access.edit_user_group("foo", "g1", True)
        transaction.commit()
        self.db.add(user)
        self.assertEqual([g.name for g in user.groups], ["g1"])

    def test_remove_user_from_group(self):
        """ Can remove a user from a group """
        user = make_user("foo", "bar", False)
        group = Group("g1")
        user.groups.add(group)
        self.db.add_all([user, group])
        transaction.commit()
        self.access.edit_user_group("foo", "g1", False)
        transaction.commit()
        self.db.add(user)
        self.assertEqual(len(user.groups), 0)

    def test_create_group(self):
        """ Can create a group """
        self.access.create_group("g1")
        transaction.commit()
        group = self.db.query(Group).first()
        self.assertIsNotNone(group)
        self.assertEqual(group.name, "g1")

    def test_delete_group(self):
        """ Can delete groups """
        user = make_user("foo", "bar")
        group = Group("foobar")
        user.groups.add(group)
        self.db.add_all([user, group])
        transaction.commit()
        self.access.edit_group_permission("pkg1", "foobar", "read", True)
        transaction.commit()
        self.access.delete_group("foobar")
        transaction.commit()
        count = self.db.query(Group).count()
        self.assertEqual(count, 0)
        count = self.db.query(association_table).count()
        self.assertEqual(count, 0)

    def test_grant_user_read_permission(self):
        """ Can give users read permissions on a package """
        user = make_user("foo", "bar", False)
        self.db.add(user)
        transaction.commit()
        self.access.edit_user_permission("pkg1", "foo", "read", True)
        transaction.commit()
        self.db.add(user)
        self.assertEqual(len(user.permissions), 1)
        perm = user.permissions[0]
        self.assertEqual(perm.package, "pkg1")
        self.assertTrue(perm.read)
        self.assertFalse(perm.write)

    def test_grant_user_write_permission(self):
        """ Can give users write permissions on a package """
        user = make_user("foo", "bar", False)
        self.db.add(user)
        transaction.commit()
        self.access.edit_user_permission("pkg1", "foo", "write", True)
        transaction.commit()
        self.db.add(user)
        self.assertEqual(len(user.permissions), 1)
        perm = user.permissions[0]
        self.assertEqual(perm.package, "pkg1")
        self.assertFalse(perm.read)
        self.assertTrue(perm.write)

    def test_grant_user_bad_permission(self):
        """ Attempting to grant a bad permission raises ValueError """
        user = make_user("foo", "bar", False)
        self.db.add(user)
        transaction.commit()
        with self.assertRaises(ValueError):
            self.access.edit_user_permission("pkg1", "foo", "wiggle", True)

    def test_revoke_user_permission(self):
        """ Can revoke user permissions on a package """
        user = make_user("foo", "bar", False)
        perm = UserPermission("pkg1", "foo", read=True)
        self.db.add_all([user, perm])
        transaction.commit()
        self.access.edit_user_permission("pkg1", "foo", "read", False)
        transaction.commit()
        self.db.add(user)
        self.assertEqual(len(user.permissions), 0)

    def test_grant_group_read_permission(self):
        """ Can give groups read permissions on a package """
        g = Group("foo")
        self.db.add(g)
        transaction.commit()
        self.access.edit_group_permission("pkg1", "foo", "read", True)
        transaction.commit()
        self.db.add(g)
        self.assertEqual(len(g.permissions), 1)
        perm = g.permissions[0]
        self.assertEqual(perm.package, "pkg1")
        self.assertTrue(perm.read)
        self.assertFalse(perm.write)

    def test_grant_group_write_permission(self):
        """ Can give groups write permissions on a package """
        g = Group("foo")
        self.db.add(g)
        transaction.commit()
        self.access.edit_group_permission("pkg1", "foo", "write", True)
        transaction.commit()
        self.db.add(g)
        self.assertEqual(len(g.permissions), 1)
        perm = g.permissions[0]
        self.assertEqual(perm.package, "pkg1")
        self.assertFalse(perm.read)
        self.assertTrue(perm.write)

    def test_grant_group_bad_permission(self):
        """ Attempting to grant a bad permission raises ValueError """
        g = Group("foo")
        self.db.add(g)
        transaction.commit()
        with self.assertRaises(ValueError):
            self.access.edit_group_permission("pkg1", "foo", "wiggle", True)

    def test_revoke_group_permission(self):
        """ Can revoke group permissions on a package """
        g = Group("foo")
        perm = GroupPermission("pkg1", "foo", read=True)
        self.db.add_all([g, perm])
        transaction.commit()
        self.access.edit_group_permission("pkg1", "foo", "read", False)
        transaction.commit()
        self.db.add(g)
        self.assertEqual(len(g.permissions), 0)

    def test_enable_registration(self):
        """ Can set the 'enable registration' flag """
        self.access.set_allow_register(True)
        self.assertTrue(self.access.allow_register())
        self.access.set_allow_register(False)
        self.assertFalse(self.access.allow_register())

    def test_dump(self):
        """ Can dump all data to json format """
        user1 = make_user("user1", "user1", True)
        user2 = make_user("user2", "user2", False)
        user3 = make_user("user3", "user3", False)
        user3.admin = True
        self.db.add_all([user1, user2, user3])
        transaction.commit()
        self.access.set_allow_register(False)
        self.access.create_group("g1")
        self.access.create_group("g2")
        self.access.edit_user_group("user2", "g1", True)
        self.access.edit_user_group("user2", "g2", True)
        self.access.edit_user_group("user3", "g2", True)
        self.access.edit_user_permission("pkg1", "user2", "read", True)
        self.access.edit_user_permission("pkg2", "user3", "read", True)
        self.access.edit_user_permission("pkg2", "user3", "write", True)
        self.access.edit_group_permission("pkg1", "g1", "read", True)
        self.access.edit_group_permission("pkg2", "g2", "read", True)
        self.access.edit_group_permission("pkg2", "g2", "write", True)

        data = self.access.dump()

        self.assertFalse(data["allow_register"])

        # users
        self.assertEqual(len(data["users"]), 2)
        for user in data["users"]:
            self.assertTrue(pwd_context.verify(user["username"], user["password"]))
            self.assertFalse(user["admin"] ^ (user["username"] == "user3"))

        # pending users
        self.assertEqual(len(data["pending_users"]), 1)
        user = data["pending_users"][0]
        self.assertTrue(pwd_context.verify(user["username"], user["password"]))

        # groups
        self.assertEqual(len(data["groups"]), 2)
        self.assertItemsEqual(data["groups"]["g1"], ["user2"])
        self.assertItemsEqual(data["groups"]["g2"], ["user2", "user3"])

        # user package perms
        self.assertEqual(
            data["packages"]["users"],
            {"pkg1": {"user2": ["read"]}, "pkg2": {"user3": ["read", "write"]}},
        )

        # group package perms
        self.assertEqual(
            data["packages"]["groups"],
            {"pkg1": {"g1": ["read"]}, "pkg2": {"g2": ["read", "write"]}},
        )

    def test_load(self):
        """ Access control can load universal format data """
        user1 = make_user("user1", "user1", True)
        user2 = make_user("user2", "user2", False)
        user3 = make_user("user3", "user3", False)
        user3.admin = True
        self.db.add_all([user1, user2, user3])
        transaction.commit()
        self.access.set_allow_register(False)
        self.access.create_group("g1")
        self.access.create_group("g2")
        self.access.edit_user_group("user2", "g1", True)
        self.access.edit_user_group("user2", "g2", True)
        self.access.edit_user_group("user3", "g2", True)
        self.access.edit_user_permission("pkg1", "user2", "read", True)
        self.access.edit_user_permission("pkg2", "user3", "read", True)
        self.access.edit_user_permission("pkg2", "user3", "write", True)
        self.access.edit_group_permission("pkg1", "g1", "read", True)
        self.access.edit_group_permission("pkg2", "g2", "read", True)
        self.access.edit_group_permission("pkg2", "g2", "write", True)
        transaction.commit()

        data1 = self.access.dump()

        self.access.db.close()
        self.db.close()
        self._drop_and_recreate()
        kwargs = SQLAccessBackend.configure(self.settings)
        self.access = SQLAccessBackend(MagicMock(), **kwargs)
        self.access.load(data1)
        data2 = self.access.dump()

        def assert_nice_equals(obj1, obj2):
            """ Assertion that handles unordered lists inside dicts """
            if isinstance(obj1, dict):
                self.assertEqual(len(obj1), len(obj2))
                for key, val in obj1.items():
                    assert_nice_equals(val, obj2[key])
            elif isinstance(obj1, list):
                self.assertItemsEqual(obj1, obj2)
            else:
                self.assertEqual(obj1, obj2)

        assert_nice_equals(data2, data1)

        # Load operation should be idempotent
        self.access.load(data2)
        data3 = self.access.dump()
        assert_nice_equals(data3, data2)

    def test_save_unicode(self):
        """ register() can accept a username with unicode """
        username, passw = "foo™", "bar™"
        self.access.register(username, passw)
        transaction.commit()
        user = self.db.query(User).first()
        self.assertEqual(user.username, username)
        self.assertTrue(pwd_context.verify(passw, user.password))

    def test_check_health_success(self):
        """ check_health returns True for good connection """
        ok, msg = self.access.check_health()
        self.assertTrue(ok)

    def test_check_health_fail(self):
        """ check_health returns False for bad connection """
        dbmock = self.access._db = MagicMock()

        def throw(*_, **__):
            """ Throw an exception """
            raise SQLAlchemyError("DB exception")

        dbmock.query.side_effect = throw
        ok, msg = self.access.check_health()
        self.assertFalse(ok)


class TestMySQLBackend(TestSQLiteBackend):
    """ Test the SQLAlchemy access backend on a MySQL DB """

    DB_URL = "mysql://root@127.0.0.1:3306/test?charset=utf8mb4"


class TestPostgresBackend(TestSQLiteBackend):
    """ Test the SQLAlchemy access backend on a Postgres DB """

    DB_URL = "postgresql://postgres@127.0.0.1:5432/postgres"


class TestLDAPBackend(BaseACLTest):
    @classmethod
    def setUpClass(cls):
        super(TestLDAPBackend, cls).setUpClass()
        l = ldap.initialize("ldap://localhost")
        try:
            l.simple_bind_s("", "")
        except ldap.SERVER_DOWN:
            raise unittest.SkipTest("Couldn't connect to LDAP")

    def setUp(self):
        super(TestLDAPBackend, self).setUp()
        self.backend = self._backend()

    def _backend(self, settings_override=None):
        """ Wrapper to instantiate a LDAPAccessBackend """
        settings = {
            "auth.ldap.url": "ldap://localhost/",
            "auth.ldap.cache_time": 0,
            "auth.ldap.service_dn": "cn=admin,dc=example,dc=org",
            "auth.ldap.service_password": "admin",
            "auth.ldap.base_dn": "dc=example,dc=org",
            "auth.ldap.user_search_filter": "(uid={username})",
            "auth.ldap.admin_field": "memberOf",
            "auth.ldap.admin_value": ["cn=pypicloud_admin,dc=example,dc=org"],
        }
        settings.update(settings_override or {})
        settings = dict(((k, v) for (k, v) in settings.items() if v is not None))
        kwargs = LDAPAccessBackend.configure(settings)
        request = DummyRequest()
        request.userid = None
        return LDAPAccessBackend(request, **kwargs)

    def test_verify(self):
        """ Users can log in with correct password """
        valid = self.backend.verify_user("pypidev", "pypidev")
        self.assertTrue(valid)

    def test_no_verify(self):
        """ Verification fails with wrong password """
        valid = self.backend.verify_user("pypidev", "foobarz")
        self.assertFalse(valid)

    def test_verify_no_user(self):
        """ Verify fails if user is unknown """
        valid = self.backend.verify_user("notreal", "foobar")
        self.assertFalse(valid)

    def test_admin(self):
        """ Specified users have 'admin' permissions """
        self.assertTrue(self.backend.is_admin("pypiadmin"))

    def test_not_admin(self):
        """ Only specified users have 'admin' permissions """
        self.assertFalse(self.backend.is_admin("pypidev"))

    def test_user_dn_format(self):
        """ Can use user_dn_format instead of base_dn """
        backend = self._backend(
            {
                "auth.ldap.user_dn_format": "uid={username},dc=example,dc=org",
                "auth.ldap.base_dn": None,
                "auth.ldap.user_search_filter": None,
            }
        )
        valid = backend.verify_user("pypidev", "pypidev")
        self.assertTrue(valid)

    def test_admin_group_dn(self):
        """ Can use admin_group_dn to check for admin privs """
        backend = self._backend(
            {
                "auth.ldap.user_dn_format": "uid={username},dc=example,dc=org",
                "auth.ldap.base_dn": None,
                "auth.ldap.user_search_filter": None,
                "auth.ldap.admin_field": None,
                "auth.ldap.admin_value": None,
                "auth.ldap.admin_group_dn": "cn=pypicloud_admin,dc=example,dc=org",
            }
        )
        self.assertTrue(backend.is_admin("pypiadmin"))


class BaseLDAPTest(BaseACLTest):
    """ Base class for LDAP tests that enable mocking the LDAP directory """

    @classmethod
    def setUpClass(cls):
        super(BaseLDAPTest, cls).setUpClass()
        test = ("o=test", {"o": ["test"], "objectClass": ["top"]})
        users = ("ou=users,o=test", {"ou": ["users"], "objectClass": ["top"]})
        admin_list = (
            "cn=adminlist,o=test",
            {
                "cn": ["adminlist"],
                "admins": ["cn=admin,ou=users,o=test"],
                "objectClass": ["top"],
            },
        )
        service = (
            "cn=service,ou=users,o=test",
            {"cn": ["service"], "userPassword": ["snerp"], "objectClass": ["top"]},
        )
        u1 = (
            "cn=u1,ou=users,o=test",
            {"cn": ["u1"], "userPassword": ["foobar"], "objectClass": ["top"]},
        )
        admin = (
            "cn=admin,ou=users,o=test",
            {
                "cn": ["admin"],
                "userPassword": ["toor"],
                "roles": ["admin"],
                "objectClass": ["top"],
            },
        )
        directory = dict([test, users, admin_list, service, u1, admin])
        cls.mockldap = MockLdap(directory)

    @classmethod
    def tearDownClass(cls):
        super(BaseLDAPTest, cls).tearDownClass()
        del cls.mockldap

    def setUp(self):
        super(BaseLDAPTest, self).setUp()
        self.mockldap.start()
        self.backend = self._backend()

    def tearDown(self):
        super(BaseLDAPTest, self).tearDown()
        self.mockldap.stop()

    def _backend(self, settings_override=None):
        """ Wrapper to instantiate a LDAPAccessBackend """
        settings = {
            "auth.ldap.url": "ldap://localhost/",
            "auth.ldap.service_dn": "cn=service,ou=users,o=test",
            "auth.ldap.service_password": "snerp",
            "auth.ldap.base_dn": "ou=users,o=test",
            "auth.ldap.user_search_filter": "(cn={username})",
            "auth.ldap.admin_field": "roles",
            "auth.ldap.admin_value": ["admin"],
        }
        settings.update(settings_override or {})
        settings = dict(((k, v) for (k, v) in settings.items() if v is not None))
        kwargs = LDAPAccessBackend.configure(settings)
        request = DummyRequest()
        request.userid = None
        return LDAPAccessBackend(request, **kwargs)


class TestLDAPMockBackend(BaseLDAPTest):
    """ Test the LDAP access backend by mocking LDAP """

    def test_verify(self):
        """ Users can log in with correct password """
        valid = self.backend.verify_user("u1", "foobar")
        self.assertTrue(valid)

    def test_no_verify(self):
        """ Verification fails with wrong password """
        valid = self.backend.verify_user("u1", "foobarz")
        self.assertFalse(valid)

    def test_verify_no_user(self):
        """ Verify fails if user is unknown """
        valid = self.backend.verify_user("notreal", "foobar")
        self.assertFalse(valid)

    def test_disallow_anonymous_bind(self):
        """ Users cannot log in with empty password """
        valid = self.backend.verify_user("u1", "")
        self.assertFalse(valid)

    def test_admin(self):
        """ Specified users have 'admin' permissions """
        self.assertTrue(self.backend.is_admin("admin"))

    def test_not_admin(self):
        """ Only specified users have 'admin' permissions """
        self.assertFalse(self.backend.is_admin("u1"))

    def test_need_admin(self):
        """ LDAP backend is immutable and never needs admin """
        self.assertFalse(self.backend.need_admin())

    def test_single_user_data(self):
        """ Get data for a single user """
        user = self.backend.user_data("u1")
        self.assertItemsEqual(user, {"username": "u1", "admin": False, "groups": []})

    def test_service_username(self):
        """ service_username allows the service account to be admin """
        backend = self._backend({"auth.ldap.service_username": "root"})
        user = backend.user_data("root")
        self.assertEqual(user, {"username": "root", "admin": True, "groups": []})

    def test_allowed_permissions(self):
        """ Default settings will only allow authenticated to read and fallback"""
        perms = self.backend.allowed_permissions("mypkg")
        self.assertEqual(perms, {Authenticated: ("read", "fallback")})

    def test_package_fallback_disallowed(self):
        """ If package is in disallow_fallback list, it won't have fallback permissions """
        self.backend.default_read = ["authenticated"]
        self.backend.disallow_fallback = ["anypkg"]
        perms = self.backend.allowed_permissions("anypkg")
        self.assertEqual(perms, {Authenticated: ("read",)})

    def test_user_package_perms(self):
        """ No user package perms in LDAP """
        perms = self.backend.user_package_permissions("u1")
        self.assertEqual(perms, [])

    def test_group_package_perms(self):
        """ No group package perms in LDAP """
        perms = self.backend.group_package_permissions("group")
        self.assertEqual(perms, [])

    def test_user_dn_format(self):
        """ Can use user_dn_format instead of base_dn """
        backend = self._backend(
            {
                "auth.ldap.user_dn_format": "cn={username},ou=users,o=test",
                "auth.ldap.base_dn": None,
                "auth.ldap.user_search_filter": None,
            }
        )
        valid = backend.verify_user("u1", "foobar")
        self.assertTrue(valid)

    def test_only_user_dn_format(self):
        """ Cannot use user_dn_format with base_dn """
        with self.assertRaises(ValueError):
            self._backend({"auth.ldap.user_dn_format": "cn={username},ou=users,o=test"})

    def test_mandatory_search(self):
        """ Must use user_dn_format or base_dn """
        with self.assertRaises(ValueError):
            self._backend(
                {"auth.ldap.base_dn": None, "auth.ldap.user_search_filter": None}
            )

    def test_check_health_success(self):
        """ check_health returns True for good connection """
        ok, msg = self.backend.check_health()
        self.assertTrue(ok)

    def test_check_health_fail(self):
        """ check_health returns False for bad connection """

        def throw(*_, **__):
            """ Throw an exception """
            raise ldap.LDAPError("LDAP exception")

        self.backend.conn = MagicMock()
        self.backend.conn.test_connection.side_effect = throw
        ok, msg = self.backend.check_health()
        self.assertFalse(ok)


class TestMockLDAPBackendWithConfig(BaseLDAPTest):

    """ Test the LDAP backend falling back to config file for groups/permissions """

    def _backend(self, settings_override=None):
        settings = {"auth.ldap.fallback": "config"}
        settings.update(settings_override or {})
        return super(TestMockLDAPBackendWithConfig, self)._backend(settings)

    def test_verify(self):
        """ Users can log in with correct password """
        valid = self.backend.verify_user("u1", "foobar")
        self.assertTrue(valid)

    def test_no_verify(self):
        """ Verification fails with wrong password """
        valid = self.backend.verify_user("u1", "foobarz")
        self.assertFalse(valid)

    def test_verify_no_user(self):
        """ Verify fails if user is unknown """
        valid = self.backend.verify_user("notreal", "foobar")
        self.assertFalse(valid)

    def test_admin(self):
        """ Specified users have 'admin' permissions """
        self.assertTrue(self.backend.is_admin("admin"))

    def test_not_admin(self):
        """ Only specified users have 'admin' permissions """
        self.assertFalse(self.backend.is_admin("u1"))

    def test_group_members(self):
        """ Fetch all members of a group """
        settings = {"group.g1": "u1 u2 u3"}
        backend = self._backend(settings)
        self.assertItemsEqual(backend.group_members("g1"), ["u1", "u2", "u3"])

    def test_all_group_permissions(self):
        """ Fetch all group permissions on a package """
        settings = {"package.mypkg.group.g1": "r", "package.mypkg.group.g2": "rw"}
        backend = self._backend(settings)
        perms = backend.group_permissions("mypkg")
        self.assertEqual(perms, {"g1": ["read"], "g2": ["read", "write"]})

    def test_all_user_perms(self):
        """ Fetch permissions on a package for all users """
        settings = {"package.mypkg.user.u1": "r", "package.mypkg.user.u2": "rw"}
        backend = self._backend(settings)
        perms = backend.user_permissions("mypkg")
        self.assertEqual(perms, {"u1": ["read"], "u2": ["read", "write"]})

    def test_user_package_perms(self):
        """ Fetch all packages a user has permissions on """
        settings = {
            "package.pkg1.user.u1": "r",
            "package.pkg2.user.u1": "rw",
            "unrelated.field": "",
        }
        backend = self._backend(settings)
        packages = backend.user_package_permissions("u1")
        self.assertItemsEqual(
            packages,
            [
                {"package": "pkg1", "permissions": ["read"]},
                {"package": "pkg2", "permissions": ["read", "write"]},
            ],
        )

    def test_long_user_package_perms(self):
        """ Can encode user package permissions in verbose form """
        settings = {
            "package.pkg1.user.u1": "read ",
            "package.pkg2.user.u1": "read write",
            "unrelated.field": "",
        }
        backend = self._backend(settings)
        packages = backend.user_package_permissions("u1")
        self.assertItemsEqual(
            packages,
            [
                {"package": "pkg1", "permissions": ["read"]},
                {"package": "pkg2", "permissions": ["read", "write"]},
            ],
        )

    def test_group_package_perms(self):
        """ Fetch all packages a group has permissions on """
        settings = {
            "package.pkg1.group.g1": "r",
            "package.pkg2.group.g1": "rw",
            "unrelated.field": "",
        }
        backend = self._backend(settings)
        packages = backend.group_package_permissions("g1")
        self.assertItemsEqual(
            packages,
            [
                {"package": "pkg1", "permissions": ["read"]},
                {"package": "pkg2", "permissions": ["read", "write"]},
            ],
        )

    def test_user_data(self):
        """ Retrieve all users """
        settings = {"user.u1": "_", "user.bar": "_"}
        backend = self._backend(settings)
        users = backend.user_data()
        self.assertItemsEqual(
            users,
            [{"username": "u1", "admin": False}, {"username": "bar", "admin": False}],
        )

    def test_single_user_data(self):
        """ Get data for a single user """
        settings = {"user.admin": "pass", "group.foobars": ["admin"]}
        backend = self._backend(settings)
        user = backend.user_data("admin")
        self.assertEqual(
            user, {"username": "admin", "admin": True, "groups": ["foobars"]}
        )


class TestAWSSecretsManagerBackend(unittest.TestCase):
    """ Tests for the AWS Secrets Manager access backend """

    @classmethod
    def setUpClass(cls):
        super(TestAWSSecretsManagerBackend, cls).setUpClass()
        cls.settings = {"auth.secret_id": "sekrit"}
        patch.object(aws_secrets_manager, "boto3").start()
        cls.kwargs = aws_secrets_manager.AWSSecretsManagerAccessBackend.configure(
            cls.settings
        )

    @classmethod
    def tearDownClass(cls):
        super(TestAWSSecretsManagerBackend, cls).tearDownClass()
        patch.stopall()

    def setUp(self):
        super(TestAWSSecretsManagerBackend, self).setUp()
        transaction.begin()
        request = MagicMock()
        request.tm = transaction.manager
        self.access = aws_secrets_manager.AWSSecretsManagerAccessBackend(
            request, **self.kwargs
        )
        self.client = self.kwargs["client"]
        self.client.get_secret_value.side_effect = lambda *_, **__: {
            "SecretString": json.dumps(self._data)
        }
        self._data = {
            "users": {
                # password is 'asdf'
                "admin": "$6$rounds=1000$Q5rf4IcKLTpMw.dN$xl/4AxlYZkSx9w78BWXBA1BwbexhvN5EN800Rh47HllK1zEamYNpjIYC4rHDImKYJEBvp72qoD0wkYYCR7Cvy.",
                "user": "$6$rounds=1000$Q5rf4IcKLTpMw.dN$xl/4AxlYZkSx9w78BWXBA1BwbexhvN5EN800Rh47HllK1zEamYNpjIYC4rHDImKYJEBvp72qoD0wkYYCR7Cvy.",
            },
            "groups": {"group1": ["admin"], "group2": ["admin", "user"]},
            "packages": {
                "pkg1": {
                    "users": {"admin": ["read", "write"], "user": ["read"]},
                    "groups": {"group2": ["read"]},
                },
                "pkg2": {
                    "users": {"admin": ["read"]},
                    "groups": {"group1": ["read", "write"]},
                },
            },
            "admins": ["admin"],
        }

    def test_verify(self):
        """ Verify login credentials against database """
        valid = self.access.verify_user("user", "asdf")
        self.assertTrue(valid)

        valid = self.access.verify_user("not_a_user", "asdf")
        self.assertFalse(valid)

        valid = self.access.verify_user("user", "barrrr")
        self.assertFalse(valid)

    def test_verify_pending(self):
        """ Pending users fail to verify """
        self._data["pending_users"] = {"user2": self._data["users"]["user"]}
        valid = self.access.verify_user("user2", "asdf")
        self.assertFalse(valid)

    def test_admin(self):
        """ Retrieve admin status from database """
        is_admin = self.access.is_admin("admin")
        self.assertTrue(is_admin)

    def test_user_groups(self):
        """ Retrieve a user's groups from database """
        groups = self.access.groups("user")
        self.assertItemsEqual(groups, ["group2"])

    def test_groups(self):
        """ Retrieve all groups from database """
        groups = self.access.groups()
        self.assertItemsEqual(groups, ["group1", "group2"])

    def test_group_members(self):
        """ Fetch all members of a group """
        users = self.access.group_members("group2")
        self.assertItemsEqual(users, ["admin", "user"])

    def test_all_user_permissions(self):
        """ Retrieve all user permissions on package from database """
        perms = self.access.user_permissions("pkg1")
        self.assertEqual(perms, {"user": ["read"], "admin": ["read", "write"]})

    def test_all_group_permissions(self):
        """ Retrieve all group permissions from database """
        perms = self.access.group_permissions("pkg1")
        self.assertEqual(perms, {"group2": ["read"]})

    def test_user_package_perms(self):
        """ Fetch all packages a user has permissions on """
        perms = self.access.user_package_permissions("user")
        self.assertEqual(perms, [{"package": "pkg1", "permissions": ["read"]}])

    def test_group_package_perms(self):
        """ Fetch all packages a group has permissions on """
        perms = self.access.group_package_permissions("group1")
        self.assertEqual(perms, [{"package": "pkg2", "permissions": ["read", "write"]}])

    def test_user_data(self):
        """ Retrieve all users """
        users = self.access.user_data()
        self.assertItemsEqual(
            users,
            [
                {"username": "admin", "admin": True},
                {"username": "user", "admin": False},
            ],
        )

    def test_single_user_data(self):
        """ Retrieve a single user's data """
        user = self.access.user_data("user")
        self.assertEqual(
            user, {"username": "user", "admin": False, "groups": ["group2"]}
        )

    def test_no_need_admin(self):
        """ If admin exists, don't need an admin """
        self.assertFalse(self.access.need_admin())

    def test_need_admin(self):
        """ If admin doesn't exist, need an admin """
        del self._data["admins"]
        self.assertTrue(self.access.need_admin())

    # Tests for mutable backend methods

    def test_register(self):
        """ Register a new user """
        self.access.register("foo", "bar")
        self.assertTrue("foo" in self.access._db["pending_users"])
        self.assertTrue(
            pwd_context.verify("bar", self.access._db["pending_users"]["foo"])
        )

    def test_pending(self):
        """ Registering a user puts them in pending list """
        self.access.register("foo", "bar")
        users = self.access.pending_users()
        self.assertEqual(users, ["foo"])

    def test_save_on_commit(self):
        """ Only save the data on transaction commit """
        self.access.register("foo", "bar")
        self.client.update_secret.assert_not_called()
        transaction.commit()
        self.client.update_secret.assert_called_once()

    def test_pending_not_in_users(self):
        """ Pending users are not listed in all_users """
        del self._data["users"]
        self.access.register("foo", "bar")
        users = self.access.user_data()
        self.assertEqual(users, [])

    def test_approve(self):
        """ Approving user marks them as not pending """
        self.access.register("foo", "bar")
        self.access.approve_user("foo")
        self.assertFalse("foo" in self.access._db["pending_users"])
        self.assertTrue("foo" in self.access._db["users"])

    def test_edit_password(self):
        """ Users can edit their passwords """
        self.access.edit_user_password("user", "baz")
        self.assertTrue(self.access.verify_user("user", "baz"))

    def test_delete_user(self):
        """ Can delete users """
        self.access.delete_user("user")
        self.assertIsNone(self.access.user_data("user"))
        self.assertEqual(self.access.groups("user"), [])

    def test_make_admin(self):
        """ Can make a user an admin """
        self.access.set_user_admin("user", True)
        is_admin = self.access.is_admin("user")
        self.assertTrue(is_admin)

    def test_remove_admin(self):
        """ Can demote an admin to normal user """
        self.access.set_user_admin("admin", False)
        is_admin = self.access.is_admin("admin")
        self.assertFalse(is_admin)

    def test_add_user_to_group(self):
        """ Can add a user to a group """
        self.access.edit_user_group("user", "group1", True)
        self.assertItemsEqual(self.access.groups("user"), ["group1", "group2"])

    def test_remove_user_from_group(self):
        """ Can remove a user from a group """
        self.access.edit_user_group("user", "group2", False)
        self.assertItemsEqual(self.access.groups("user"), [])

    def test_create_group(self):
        """ Can create a group """
        self.access.create_group("group3")
        self.assertItemsEqual(self.access.groups(), ["group1", "group2", "group3"])

    def test_delete_group(self):
        """ Can delete groups """
        self.access.delete_group("group1")
        self.assertItemsEqual(self.access.groups(), ["group2"])

    def test_grant_user_read_permission(self):
        """ Can give users read permissions on a package """
        del self._data["packages"]["pkg2"]["users"]
        self.access.edit_user_permission("pkg2", "user", "read", True)
        self.assertEqual(self.access.user_permissions("pkg2"), {"user": ["read"]})

    def test_grant_user_write_permission(self):
        """ Can give users write permissions on a package """
        del self._data["packages"]["pkg2"]["users"]
        self.access.edit_user_permission("pkg2", "user", "write", True)
        self.assertEqual(self.access.user_permissions("pkg2"), {"user": ["write"]})

    def test_grant_user_bad_permission(self):
        """ Attempting to grant a bad permission raises ValueError """
        with self.assertRaises(ValueError):
            self.access.edit_user_permission("pkg1", "user", "wiggle", True)

    def test_revoke_user_permission(self):
        """ Can revoke user permissions on a package """
        self.access.edit_user_permission("pkg2", "admin", "read", False)
        self.assertEqual(self.access.user_permissions("pkg2"), {})

    def test_grant_group_read_permission(self):
        """ Can give groups read permissions on a package """
        del self._data["packages"]["pkg2"]["groups"]
        self.access.edit_group_permission("pkg2", "group2", "read", True)
        self.assertEqual(self.access.group_permissions("pkg2"), {"group2": ["read"]})

    def test_grant_group_write_permission(self):
        """ Can give groups write permissions on a package """
        del self._data["packages"]["pkg2"]["groups"]
        self.access.edit_group_permission("pkg2", "group2", "write", True)
        self.assertEqual(self.access.group_permissions("pkg2"), {"group2": ["write"]})

    def test_grant_group_bad_permission(self):
        """ Attempting to grant a bad permission raises ValueError """
        with self.assertRaises(ValueError):
            self.access.edit_group_permission("pkg1", "group1", "wiggle", True)

    def test_revoke_group_permission(self):
        """ Can revoke group permissions on a package """
        self.access.edit_group_permission("pkg2", "group1", "write", False)
        self.assertEqual(self.access.group_permissions("pkg2"), {"group1": ["read"]})

    def test_enable_registration(self):
        """ Can set the 'enable registration' flag """
        self.access.set_allow_register(True)
        self.assertTrue(self.access.allow_register())
        self.access.set_allow_register(False)
        self.assertFalse(self.access.allow_register())

    def test_check_health_success(self):
        """ check_health returns True for good connection """
        ok, msg = self.access.check_health()
        self.assertTrue(ok)

    def test_check_health_fail(self):
        """ check_health returns False for bad connection """

        def throw(*_, **__):
            """ Throw an exception """
            raise Exception("secrets exception")

        self.client.get_secret_value.side_effect = throw
        ok, msg = self.access.check_health()
        self.assertFalse(ok)
