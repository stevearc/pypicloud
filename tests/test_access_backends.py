# -*- coding: utf-8 -*-
""" Tests for access backends """
from __future__ import unicode_literals
import transaction
from mock import MagicMock, patch
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.security import Everyone, Authenticated
from pyramid.testing import DummyRequest
from sqlalchemy.exc import OperationalError

from pypicloud.access import (IAccessBackend, IMutableAccessBackend,
                              ConfigAccessBackend, RemoteAccessBackend,
                              includeme, pwd_context)
from pypicloud.access.base import group_to_principal
from pypicloud.access.sql import (SQLAccessBackend, User, UserPermission,
                                  association_table, GroupPermission, Group, Base)
from pypicloud.route import Root


try:
    import unittest2 as unittest  # pylint: disable=F0401
except ImportError:
    import unittest


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
    return User(name, pwd_context.encrypt(password), pending)


class TestUtilities(unittest.TestCase):

    """ Tests for the access utilities """

    def test_group_to_principal(self):
        """ group_to_principal formats groups """
        self.assertEqual(group_to_principal('foo'), 'group:foo')
        self.assertEqual(group_to_principal('everyone'), Everyone)
        self.assertEqual(group_to_principal('authenticated'), Authenticated)

    def test_group_to_principal_twice(self):
        """ Running group_to_principal twice has no effect """
        for group in ('foo', 'everyone', 'authenticated'):
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
        if not hasattr(context, '__acl__'):
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
        patch.object(self.backend, 'verify_user').start()
        patch.object(self.backend, 'groups').start()
        patch.object(self.backend, 'is_admin').start()
        patch.object(self.backend, 'group_permissions').start()
        patch.object(self.backend, 'user_permissions').start()
        self.request.access = self.backend

    def tearDown(self):
        super(TestBaseBackend, self).tearDown()
        patch.stopall()

    def test_root_acl(self):
        """ Root ACL sets login, admin, and DENY ALL """
        root = Root(self.request)
        self.assert_allowed(root, 'login', ['admin', Authenticated])
        self.assert_allowed(root, 'admin', ['admin'])
        self.assert_allowed(root, 'arbitrary', ['admin'])

    def test_user_rw(self):
        """ Owner always has rw perms on a package """
        self.backend.user_permissions.return_value = {
            'dsa': ['read', 'write'],
        }
        acl = self.backend.get_acl('mypkg')
        self.assert_allowed(acl, 'read', ['user:dsa'])
        self.assert_allowed(acl, 'write', ['user:dsa'])

    def test_group_everyone(self):
        """ Special 'everyone' group sets perms for everyone """
        self.backend.group_permissions.return_value = {
            'everyone': ['read', 'write'],
        }
        acl = self.backend.get_acl('mypkg')
        self.assert_allowed(acl, 'read', [Everyone])
        self.assert_allowed(acl, 'write', [Everyone])

    def test_group_authenticated(self):
        """ Special 'authenticated' group sets perms for logged-in users """
        self.backend.group_permissions.return_value = {
            'authenticated': ['read', 'write'],
        }
        acl = self.backend.get_acl('mypkg')
        self.assert_allowed(acl, 'read', [Authenticated])
        self.assert_allowed(acl, 'write', [Authenticated])

    def test_group(self):
        """ Groups set perms for a 'group:<>' principal """
        self.backend.group_permissions.return_value = {
            'brotatos': ['read', 'write'],
        }
        acl = self.backend.get_acl('mypkg')
        self.assert_allowed(acl, 'read', ['group:brotatos'])
        self.assert_allowed(acl, 'write', ['group:brotatos'])

    def test_abstract_methods(self):
        """ Abstract methods raise NotImplementedError """
        access = IMutableAccessBackend(None)
        with self.assertRaises(NotImplementedError):
            access.verify_user('a', 'b')
        with self.assertRaises(NotImplementedError):
            access.groups()
        with self.assertRaises(NotImplementedError):
            access.group_members('a')
        with self.assertRaises(NotImplementedError):
            access.is_admin('a')
        with self.assertRaises(NotImplementedError):
            access.group_permissions('a')
        with self.assertRaises(NotImplementedError):
            access.user_permissions('a')
        with self.assertRaises(NotImplementedError):
            access.user_package_permissions('a')
        with self.assertRaises(NotImplementedError):
            access.group_package_permissions('a')
        with self.assertRaises(NotImplementedError):
            access.user_data()
        with self.assertRaises(NotImplementedError):
            access.allow_register()
        with self.assertRaises(NotImplementedError):
            access.set_allow_register(True)
        with self.assertRaises(NotImplementedError):
            access.register('a', 'b')
        with self.assertRaises(NotImplementedError):
            access.pending_users()
        with self.assertRaises(NotImplementedError):
            access.approve_user('a')
        with self.assertRaises(NotImplementedError):
            access.edit_user_password('a', 'b')
        with self.assertRaises(NotImplementedError):
            access.delete_user('a')
        with self.assertRaises(NotImplementedError):
            access.set_user_admin('a', True)
        with self.assertRaises(NotImplementedError):
            access.edit_user_group('a', 'a', 'add')
        with self.assertRaises(NotImplementedError):
            access.create_group('a')
        with self.assertRaises(NotImplementedError):
            access.delete_group('a')
        with self.assertRaises(NotImplementedError):
            access.edit_user_permission('a', 'b', 'c', True)
        with self.assertRaises(NotImplementedError):
            access.edit_group_permission('a', 'b', 'c', True)

    def test_need_admin(self):
        """ need_admin is True if no admins """
        access = IMutableAccessBackend(None)
        with patch.object(access, 'user_data') as user_data:
            user_data.return_value = [{'admin': False}]
            self.assertTrue(access.need_admin())

    def test_no_need_admin(self):
        """ need_admin is False if 1+ admins """
        access = IMutableAccessBackend(None)
        with patch.object(access, 'user_data') as user_data:
            user_data.return_value = [{'admin': False}, {'admin': True}]
            self.assertFalse(access.need_admin())

    def test_load_remote_backend(self):
        """ keyword 'remote' loads RemoteBackend """
        config = MagicMock()
        config.get_settings.return_value = {
            'pypi.access_backend': 'remote',
            'auth.backend_server': 'http://example.com',
        }
        includeme(config)
        config.add_request_method.assert_called_with(
            PartialEq(RemoteAccessBackend),
            name='access', reify=True)

    def test_load_sql_backend(self):
        """ keyword 'sql' loads SQLBackend """
        config = MagicMock()
        config.get_settings.return_value = {
            'auth.db.url': 'sqlite://',
            'pypi.access_backend': 'sql',
        }
        includeme(config)
        config.add_request_method.assert_called_with(
            PartialEq(SQLAccessBackend),
            name='access', reify=True)

    def test_load_arbitrary_backend(self):
        """ Can pass dotted path to load arbirary backend """
        config = MagicMock()
        config.get_settings.return_value = {
            'auth.db.url': 'sqlite://',
            'pypi.access_backend': 'pypicloud.access.sql.SQLAccessBackend',
        }
        includeme(config)
        config.add_request_method.assert_called_with(
            PartialEq(SQLAccessBackend),
            name='access', reify=True)

    def test_admin_has_permission(self):
        """ Admins always have permission """
        self.request.userid = 'abc'
        access = IAccessBackend(self.request)
        access.is_admin = lambda x: True
        self.assertTrue(access.has_permission('p1', 'write'))

    def test_has_permission_default_read(self):
        """ If no user/group permissions on a package, use default_read """
        self.backend.default_read = ['everyone', 'authenticated']
        self.backend.default_write = []
        perms = self.backend.allowed_permissions('anypkg')
        self.assertEqual(perms, {Everyone: ('read',),
                                 Authenticated: ('read',)})

    def test_has_permission_default_write(self):
        """ If no user/group permissions on a package, use default_write """
        self.backend.default_read = ['authenticated']
        self.backend.default_write = ['authenticated']
        perms = self.backend.allowed_permissions('anypkg')
        self.assertEqual(perms, {Authenticated: ('read', 'write')})

    def test_admin_principal(self):
        """ Admin user has the 'admin' principal """
        access = IAccessBackend(None)
        access.is_admin = lambda x: True
        with patch.object(access, 'groups') as groups:
            groups.return_value = ['brotatos']
            principals = access.user_principals('abc')
        self.assertItemsEqual(principals, [Everyone, Authenticated, 'admin',
                                           'group:brotatos', 'user:abc'])

    def test_load(self):
        """ Base backend has no default implementation for load() """
        access = IAccessBackend(None)
        with self.assertRaises(TypeError):
            access.load({})


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
            'group.g1': 'u1 u2 u3',
            'group.g2': 'u2 u3 u4',
            'unrelated': 'weeeeee',
        }
        backend = self._backend(settings)
        self.assertItemsEqual(backend.groups(), ['g1', 'g2'])
        self.assertItemsEqual(backend.groups('u1'), ['g1'])
        self.assertItemsEqual(backend.groups('u2'), ['g1', 'g2'])
        self.assertItemsEqual(backend.groups('u3'), ['g1', 'g2'])
        self.assertItemsEqual(backend.groups('u4'), ['g2'])

    def test_verify(self):
        """ Users can log in with correct password """
        settings = {
            'user.u1': pwd_context.encrypt('foobar'),
        }
        backend = self._backend(settings)
        valid = backend.verify_user('u1', 'foobar')
        self.assertTrue(valid)

    def test_no_verify(self):
        """ Verification fails with wrong password """
        settings = {
            'user.u1': pwd_context.encrypt('foobar'),
        }
        backend = self._backend(settings)
        valid = backend.verify_user('u1', 'foobarz')
        self.assertFalse(valid)

    def test_group_members(self):
        """ Fetch all members of a group """
        settings = {
            'group.g1': 'u1 u2 u3',
        }
        backend = self._backend(settings)
        self.assertItemsEqual(backend.group_members('g1'),
                              ['u1', 'u2', 'u3'])

    def test_all_group_permissions(self):
        """ Fetch all group permissions on a package """
        settings = {
            'package.mypkg.group.g1': 'r',
            'package.mypkg.group.g2': 'rw',
        }
        backend = self._backend(settings)
        perms = backend.group_permissions('mypkg')
        self.assertEqual(perms, {'g1': ['read'], 'g2': ['read', 'write']})

    def test_group_permissions(self):
        """ Fetch permissions for a single group on a package """
        settings = {
            'package.mypkg.group.g1': 'r',
            'package.mypkg.group.g2': 'rw',
        }
        backend = self._backend(settings)
        perms = backend.group_permissions('mypkg', 'g1')
        self.assertEqual(perms, ['read'])

    @patch('pypicloud.access.base.effective_principals')
    def test_everyone_permission(self, principals):
        """ All users have 'everyone' permissions """
        settings = {'package.mypkg.group.everyone': 'r'}
        principals.return_value = [Everyone]
        backend = self._backend(settings)
        self.assertTrue(backend.has_permission('mypkg', 'read'))
        self.assertFalse(backend.has_permission('mypkg', 'write'))

    @patch('pypicloud.access.base.effective_principals')
    def test_authenticated_permission(self, principals):
        """ All logged-in users have 'authenticated' permissions """
        settings = {'package.mypkg.group.authenticated': 'r'}
        principals.return_value = [Authenticated]
        backend = self._backend(settings)
        self.assertTrue(backend.has_permission('mypkg', 'read'))
        self.assertFalse(backend.has_permission('mypkg', 'write'))

    def test_all_user_perms(self):
        """ Fetch permissions on a package for all users """
        settings = {
            'package.mypkg.user.u1': 'r',
            'package.mypkg.user.u2': 'rw',
        }
        backend = self._backend(settings)
        perms = backend.user_permissions('mypkg')
        self.assertEqual(perms, {'u1': ['read'], 'u2': ['read', 'write']})

    def test_user_perms(self):
        """ Fetch permissions on a package for one user """
        settings = {
            'package.mypkg.user.u1': 'r',
            'package.mypkg.user.u2': 'rw',
        }
        backend = self._backend(settings)
        perms = backend.user_permissions('mypkg', 'u1')
        self.assertEqual(perms, ['read'])

    def test_user_package_perms(self):
        """ Fetch all packages a user has permissions on """
        settings = {
            'package.pkg1.user.u1': 'r',
            'package.pkg2.user.u1': 'rw',
            'unrelated.field': '',
        }
        backend = self._backend(settings)
        packages = backend.user_package_permissions('u1')
        self.assertItemsEqual(packages, [
            {'package': 'pkg1', 'permissions': ['read']},
            {'package': 'pkg2', 'permissions': ['read', 'write']},
        ])

    def test_group_package_perms(self):
        """ Fetch all packages a group has permissions on """
        settings = {
            'package.pkg1.group.g1': 'r',
            'package.pkg2.group.g1': 'rw',
            'unrelated.field': '',
        }
        backend = self._backend(settings)
        packages = backend.group_package_permissions('g1')
        self.assertItemsEqual(packages, [
            {'package': 'pkg1', 'permissions': ['read']},
            {'package': 'pkg2', 'permissions': ['read', 'write']},
        ])

    def test_user_data(self):
        """ Retrieve all users """
        settings = {
            'user.foo': 'pass',
            'user.bar': 'pass',
            'auth.admins': ['foo'],
        }
        backend = self._backend(settings)
        users = backend.user_data()
        self.assertItemsEqual(users, [
            {
                'username': 'foo',
                'admin': True,
            },
            {
                'username': 'bar',
                'admin': False,
            },
        ])

    def test_single_user_data(self):
        """ Get data for a single user """
        settings = {
            'user.foo': 'pass',
            'auth.admins': ['foo'],
            'group.foobars': ['foo'],
        }
        backend = self._backend(settings)
        user = backend.user_data('foo')
        self.assertEqual(user, {
            'username': 'foo',
            'admin': True,
            'groups': ['foobars'],
        })

    def test_need_admin(self):
        """ Config backend is static and never needs admin """
        backend = self._backend({})
        self.assertFalse(backend.need_admin())

    def test_load(self):
        """ Config backend can load ACL and format config strings """
        settings = {
            'group.g1': 'u1 u3',
            'user.u1': 'passhash',
            'user.u2': 'hashpass',
            'user.u3': 'hashhhhh',
            'auth.admins': 'u1 u2',
            'package.pkg.user.u1': 'rw',
            'package.pkg.group.g1': 'r',
        }
        backend = self._backend(settings)
        data = backend.dump()
        config = backend.load(data)

        def parse_config(string):
            """ Parse the settings from config.ini format """
            conf = {}
            key, value = None, None
            for line in string.splitlines():
                if line.startswith(' '):
                    value += ' ' + line.strip()
                else:
                    if key is not None:
                        conf[key] = ' '.join(sorted(value.split())).strip()
                    key, value = line.split('=')
                    key = key.strip()
                    value = value.strip()
            conf[key] = ' '.join(sorted(value.split())).strip()
            return conf
        self.assertEqual(parse_config(config), settings)


class TestRemoteBackend(unittest.TestCase):

    """ Tests for the access backend that delegates calls to remote server """

    def setUp(self):
        request = DummyRequest()
        self.auth = ('user', 'pass')
        settings = {
            'auth.backend_server': 'server',
            'auth.user': self.auth[0],
            'auth.password': self.auth[1],
        }
        kwargs = RemoteAccessBackend.configure(settings)
        self.backend = RemoteAccessBackend(request, **kwargs)
        self.requests = MagicMock()
        patch.dict('sys.modules', requests=self.requests).start()

    def tearDown(self):
        patch.stopall()

    def test_verify(self):
        """ Delegate login to remote server """
        verified = self.backend.verify_user('user', 'pass')
        params = {'username': 'user', 'password': 'pass'}
        self.requests.get.assert_called_with('server/verify', params=params,
                                             auth=self.auth)
        self.assertEqual(verified, self.requests.get().json())

    def test_user_groups(self):
        """ Delegate fetching user groups to remote server """
        groups = self.backend.groups('dsa')
        params = {'username': 'dsa'}
        self.requests.get.assert_called_with(
            'server/groups', params=params, auth=self.auth)
        self.assertEqual(groups, self.requests.get().json())

    def test_all_groups(self):
        """ Delegate fetching all groups to remote server """
        groups = self.backend.groups()
        self.requests.get.assert_called_with(
            'server/groups', params={}, auth=self.auth)
        self.assertEqual(groups, self.requests.get().json())

    def test_group_members(self):
        """ Delegate fetching group members to remote server """
        groups = self.backend.group_members('g1')
        params = {'group': 'g1'}
        self.requests.get.assert_called_with('server/group_members',
                                             params=params, auth=self.auth)
        self.assertEqual(groups, self.requests.get().json())

    def test_admin(self):
        """ Query server to determine if user is admin """
        is_admin = self.backend.is_admin('dsa')
        params = {'username': 'dsa'}
        self.requests.get.assert_called_with('server/admin', params=params,
                                             auth=self.auth)
        self.assertEqual(is_admin, self.requests.get().json())

    def test_all_group_perms(self):
        """ Query server for all group permissions on a package """
        perms = self.backend.group_permissions('mypkg')
        params = {'package': 'mypkg'}
        self.requests.get.assert_called_with('server/group_permissions',
                                             params=params, auth=self.auth)
        self.assertEqual(perms, self.requests.get().json())

    def test_group_perms(self):
        """ Query server for group permissions on a package """
        perms = self.backend.group_permissions('mypkg', 'grp')
        params = {'package': 'mypkg', 'group': 'grp'}
        self.requests.get.assert_called_with('server/group_permissions',
                                             params=params, auth=self.auth)
        self.assertEqual(perms, self.requests.get().json())

    def test_all_user_perms(self):
        """ Query server for all user permissions on a package """
        perms = self.backend.user_permissions('mypkg')
        params = {'package': 'mypkg'}
        self.requests.get.assert_called_with('server/user_permissions',
                                             params=params, auth=self.auth)
        self.assertEqual(perms, self.requests.get().json())

    def test_user_perms(self):
        """ Query server for a user's permissions on a package """
        perms = self.backend.user_permissions('mypkg', 'u1')
        params = {'package': 'mypkg', 'username': 'u1'}
        self.requests.get.assert_called_with('server/user_permissions',
                                             params=params, auth=self.auth)
        self.assertEqual(perms, self.requests.get().json())

    def test_user_perms_with_username(self):
        """ Query server for a user's permissions on a package """
        perms = self.backend.user_permissions('mypkg', 'a')
        params = {'package': 'mypkg', 'username': 'a'}
        self.requests.get.assert_called_with('server/user_permissions',
                                             params=params, auth=self.auth)
        self.assertEqual(perms, self.requests.get().json())

    def test_user_data(self):
        """ Retrieve all users """
        users = self.backend.user_data()
        self.requests.get.assert_called_with('server/user_data', params=None,
                                             auth=self.auth)
        self.assertEqual(users, self.requests.get().json())

    def test_single_user_data(self):
        """ Retrieve user data """
        users = self.backend.user_data('foo')
        self.requests.get.assert_called_with('server/user_data',
                                             params={'username': 'foo'},
                                             auth=self.auth)
        self.assertEqual(users, self.requests.get().json())

    def test_user_package_perms(self):
        """ Fetch all packages a user has permissions on """
        users = self.backend.user_package_permissions('u1')
        params = {'username': 'u1'}
        self.requests.get.assert_called_with('server/user_package_permissions',
                                             params=params, auth=self.auth)
        self.assertEqual(users, self.requests.get().json())

    def test_group_package_perms(self):
        """ Fetch all packages a group has permissions on """
        groups = self.backend.group_package_permissions('g1')
        params = {'group': 'g1'}
        self.requests.get.assert_called_with(
            'server/group_package_permissions',
            params=params, auth=self.auth)
        self.assertEqual(groups, self.requests.get().json())


class TestSQLiteBackend(unittest.TestCase):
    """ Tests for the SQL access backend """

    DB_URL = 'sqlite://'

    @classmethod
    def setUpClass(cls):
        super(TestSQLiteBackend, cls).setUpClass()
        cls.settings = {
            'auth.db.url': cls.DB_URL,
        }
        try:
            cls.kwargs = SQLAccessBackend.configure(cls.settings)
        except OperationalError:
            raise unittest.SkipTest("Couldn't connect to database")

    def setUp(self):
        super(TestSQLiteBackend, self).setUp()
        self.db = self.kwargs['dbmaker']()
        self.access = SQLAccessBackend(MagicMock(), **self.kwargs)

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
        user = make_user('foo', 'bar', False)
        self.db.add(user)
        transaction.commit()
        valid = self.access.verify_user('foo', 'bar')
        self.assertTrue(valid)

        valid = self.access.verify_user('foo', 'barrrr')
        self.assertFalse(valid)

    def test_verify_pending(self):
        """ Pending users fail to verify """
        user = make_user('foo', 'bar')
        self.db.add(user)
        transaction.commit()
        valid = self.access.verify_user('foo', 'bar')
        self.assertFalse(valid)

    def test_admin(self):
        """ Retrieve admin status from database """
        user = make_user('foo', 'bar', False)
        user.admin = True
        self.db.add(user)
        transaction.commit()
        is_admin = self.access.is_admin('foo')
        self.assertTrue(is_admin)

    def test_admin_default_false(self):
        """ The default admin status is False """
        user = make_user('foo', 'bar', False)
        self.db.add(user)
        transaction.commit()
        is_admin = self.access.is_admin('foo')
        self.assertFalse(is_admin)

    def test_user_groups(self):
        """ Retrieve a user's groups from database """
        user = make_user('foo', 'bar', False)
        g1 = Group('brotatos')
        g2 = Group('sharkfest')
        user.groups.update([g1, g2])
        self.db.add_all([user, g1, g2])
        transaction.commit()
        groups = self.access.groups('foo')
        self.assertItemsEqual(groups, ['brotatos', 'sharkfest'])

    def test_groups(self):
        """ Retrieve all groups from database """
        user = make_user('foo', 'bar', False)
        g1 = Group('brotatos')
        g2 = Group('sharkfest')
        user.groups.add(g1)
        user.groups.add(g2)
        self.db.add(user)
        transaction.commit()
        groups = self.access.groups()
        self.assertItemsEqual(groups, ['brotatos', 'sharkfest'])

    def test_group_members(self):
        """ Fetch all members of a group """
        u1 = make_user('u1', 'bar', False)
        u2 = make_user('u2', 'bar', False)
        u3 = make_user('u3', 'bar', False)
        g1 = Group('g1')
        g1.users.update([u1, u2])
        self.db.add_all([u1, u2, u3, g1])
        transaction.commit()
        users = self.access.group_members('g1')
        self.assertItemsEqual(users, ['u1', 'u2'])

    def test_all_user_permissions(self):
        """ Retrieve all user permissions on package from database """
        user = make_user('foo', 'bar', False)
        user2 = make_user('foo2', 'bar', False)
        p1 = UserPermission('pkg1', 'foo', True, False)
        p2 = UserPermission('pkg1', 'foo2', True, True)
        self.db.add_all([user, user2, p1, p2])
        transaction.commit()
        perms = self.access.user_permissions('pkg1')
        self.assertEqual(perms, {
            'foo': ['read'],
            'foo2': ['read', 'write'],
        })

    def test_user_permissions(self):
        """ Retrieve a user's permissions on package from database """
        user = make_user('foo', 'bar', False)
        user2 = make_user('foo2', 'bar', False)
        p1 = UserPermission('pkg1', 'foo', True, False)
        p2 = UserPermission('pkg1', 'foo2', True, True)
        self.db.add_all([user, user2, p1, p2])
        transaction.commit()
        perms = self.access.user_permissions('pkg1', 'foo')
        self.assertEqual(perms, ['read'])

    def test_all_group_permissions(self):
        """ Retrieve all group permissions from database """
        g1 = Group('brotatos')
        g2 = Group('sharkfest')
        p1 = GroupPermission('pkg1', 'brotatos', True, False)
        p2 = GroupPermission('pkg1', 'sharkfest', True, True)
        self.db.add_all([g1, g2, p1, p2])
        transaction.commit()
        perms = self.access.group_permissions('pkg1')
        self.assertEqual(perms, {
            'brotatos': ['read'],
            'sharkfest': ['read', 'write'],
        })

    def test_group_permissions(self):
        """ Retrieve a group's permissions from database """
        g1 = Group('brotatos')
        g2 = Group('sharkfest')
        p1 = GroupPermission('pkg1', 'brotatos', True, False)
        p2 = GroupPermission('pkg1', 'sharkfest', True, True)
        self.db.add_all([g1, g2, p1, p2])
        transaction.commit()
        perms = self.access.group_permissions('pkg1', 'brotatos')
        self.assertEqual(perms, ['read'])

    def test_user_package_perms(self):
        """ Fetch all packages a user has permissions on """
        user = make_user('foo', 'bar', False)
        p1 = UserPermission('pkg1', 'foo', True, False)
        p2 = UserPermission('pkg2', 'foo', True, True)
        self.db.add_all([user, p1, p2])
        transaction.commit()
        perms = self.access.user_package_permissions('foo')
        self.assertEqual(perms, [
            {'package': 'pkg1', 'permissions': ['read']},
            {'package': 'pkg2', 'permissions': ['read', 'write']},
        ])

    def test_group_package_perms(self):
        """ Fetch all packages a group has permissions on """
        g1 = Group('foo')
        p1 = GroupPermission('pkg1', 'foo', True, False)
        p2 = GroupPermission('pkg2', 'foo', True, True)
        self.db.add_all([g1, p1, p2])
        transaction.commit()
        perms = self.access.group_package_permissions('foo')
        self.assertEqual(perms, [
            {'package': 'pkg1', 'permissions': ['read']},
            {'package': 'pkg2', 'permissions': ['read', 'write']},
        ])

    def test_user_data(self):
        """ Retrieve all users """
        u1 = make_user('foo', 'bar', False)
        u1.admin = True
        u2 = make_user('bar', 'bar', False)
        g1 = Group('foobars')
        u2.groups.add(g1)
        self.db.add_all([u1, u2, g1])
        transaction.commit()
        users = self.access.user_data()
        self.assertItemsEqual(users, [
            {'username': 'foo', 'admin': True},
            {'username': 'bar', 'admin': False},
        ])

    def test_single_user_data(self):
        """ Retrieve a single user's data """
        u1 = make_user('foo', 'bar', False)
        u1.admin = True
        g1 = Group('foobars')
        u1.groups.add(g1)
        self.db.add_all([u1, g1])
        transaction.commit()
        user = self.access.user_data('foo')
        self.assertEqual(user, {
            'username': 'foo',
            'admin': True,
            'groups': ['foobars'],
        })

    def test_no_need_admin(self):
        """ If admin exists, don't need an admin """
        user = make_user('foo', 'bar', False)
        user.admin = True
        self.db.add(user)
        transaction.commit()
        self.assertFalse(self.access.need_admin())

    def test_need_admin(self):
        """ If admin doesn't exist, need an admin """
        user = make_user('foo', 'bar', False)
        self.db.add(user)
        transaction.commit()
        self.assertTrue(self.access.need_admin())

    # Tests for mutable backend methods

    def test_register(self):
        """ Register a new user """
        self.access.register('foo', 'bar')
        transaction.commit()
        user = self.db.query(User).first()
        self.assertEqual(user.username, 'foo')
        self.assertTrue(pwd_context.verify('bar', user.password))

    def test_pending(self):
        """ Registering a user puts them in pending list """
        user = make_user('foo', 'bar')
        self.db.add(user)
        transaction.commit()
        users = self.access.pending_users()
        self.assertEqual(users, ['foo'])

    def test_pending_not_in_users(self):
        """ Pending users are not listed in all_users """
        user = make_user('foo', 'bar')
        self.db.add(user)
        transaction.commit()
        users = self.access.user_data()
        self.assertEqual(users, [])

    def test_approve(self):
        """ Approving user marks them as not pending """
        user = make_user('foo', 'bar')
        self.db.add(user)
        transaction.commit()
        self.access.approve_user('foo')
        transaction.commit()
        user = self.db.query(User).first()
        self.assertFalse(user.pending)

    def test_edit_password(self):
        """ Users can edit their passwords """
        user = make_user('foo', 'bar', False)
        self.db.add(user)
        transaction.commit()
        self.access.edit_user_password('foo', 'baz')
        transaction.commit()
        user = self.db.query(User).first()
        self.assertTrue(self.access.verify_user('foo', 'baz'))

    def test_delete_user(self):
        """ Can delete users """
        user = make_user('foo', 'bar', False)
        group = Group('foobar')
        user.groups.add(group)
        self.db.add_all([user, group])
        transaction.commit()
        self.access.delete_user('foo')
        transaction.commit()
        user = self.db.query(User).first()
        self.assertIsNone(user)
        count = self.db.query(association_table).count()
        self.assertEqual(count, 0)

    def test_make_admin(self):
        """ Can make a user an admin """
        user = make_user('foo', 'bar', False)
        self.db.add(user)
        transaction.commit()
        self.access.set_user_admin('foo', True)
        transaction.commit()
        self.db.add(user)
        self.assertTrue(user.admin)

    def test_remove_admin(self):
        """ Can demote an admin to normal user """
        user = make_user('foo', 'bar', False)
        user.admin = True
        self.db.add(user)
        transaction.commit()
        self.access.set_user_admin('foo', False)
        transaction.commit()
        self.db.add(user)
        self.assertFalse(user.admin)

    def test_add_user_to_group(self):
        """ Can add a user to a group """
        user = make_user('foo', 'bar', False)
        group = Group('g1')
        self.db.add_all([user, group])
        transaction.commit()
        self.access.edit_user_group('foo', 'g1', True)
        transaction.commit()
        self.db.add(user)
        self.assertEqual([g.name for g in user.groups], ['g1'])

    def test_remove_user_from_group(self):
        """ Can remove a user from a group """
        user = make_user('foo', 'bar', False)
        group = Group('g1')
        user.groups.add(group)
        self.db.add_all([user, group])
        transaction.commit()
        self.access.edit_user_group('foo', 'g1', False)
        transaction.commit()
        self.db.add(user)
        self.assertEqual(len(user.groups), 0)

    def test_create_group(self):
        """ Can create a group """
        self.access.create_group('g1')
        transaction.commit()
        group = self.db.query(Group).first()
        self.assertIsNotNone(group)
        self.assertEqual(group.name, 'g1')

    def test_delete_group(self):
        """ Can delete groups """
        user = make_user('foo', 'bar')
        group = Group('foobar')
        user.groups.add(group)
        self.db.add_all([user, group])
        transaction.commit()
        self.access.delete_group('foobar')
        transaction.commit()
        count = self.db.query(Group).count()
        self.assertEqual(count, 0)
        count = self.db.query(association_table).count()
        self.assertEqual(count, 0)

    def test_grant_user_read_permission(self):
        """ Can give users read permissions on a package """
        user = make_user('foo', 'bar', False)
        self.db.add(user)
        transaction.commit()
        self.access.edit_user_permission('pkg1', 'foo', 'read', True)
        transaction.commit()
        self.db.add(user)
        self.assertEqual(len(user.permissions), 1)
        perm = user.permissions[0]
        self.assertEqual(perm.package, 'pkg1')
        self.assertTrue(perm.read)
        self.assertFalse(perm.write)

    def test_grant_user_write_permission(self):
        """ Can give users write permissions on a package """
        user = make_user('foo', 'bar', False)
        self.db.add(user)
        transaction.commit()
        self.access.edit_user_permission('pkg1', 'foo', 'write', True)
        transaction.commit()
        self.db.add(user)
        self.assertEqual(len(user.permissions), 1)
        perm = user.permissions[0]
        self.assertEqual(perm.package, 'pkg1')
        self.assertFalse(perm.read)
        self.assertTrue(perm.write)

    def test_grant_user_bad_permission(self):
        """ Attempting to grant a bad permission raises ValueError """
        user = make_user('foo', 'bar', False)
        self.db.add(user)
        transaction.commit()
        with self.assertRaises(ValueError):
            self.access.edit_user_permission('pkg1', 'foo', 'wiggle', True)

    def test_revoke_user_permission(self):
        """ Can revoke user permissions on a package """
        user = make_user('foo', 'bar', False)
        perm = UserPermission('pkg1', 'foo', read=True)
        self.db.add_all([user, perm])
        transaction.commit()
        self.access.edit_user_permission('pkg1', 'foo', 'read', False)
        transaction.commit()
        self.db.add(user)
        self.assertEqual(len(user.permissions), 0)

    def test_grant_group_read_permission(self):
        """ Can give groups read permissions on a package """
        g = Group('foo')
        self.db.add(g)
        transaction.commit()
        self.access.edit_group_permission('pkg1', 'foo', 'read', True)
        transaction.commit()
        self.db.add(g)
        self.assertEqual(len(g.permissions), 1)
        perm = g.permissions[0]
        self.assertEqual(perm.package, 'pkg1')
        self.assertTrue(perm.read)
        self.assertFalse(perm.write)

    def test_grant_group_write_permission(self):
        """ Can give groups write permissions on a package """
        g = Group('foo')
        self.db.add(g)
        transaction.commit()
        self.access.edit_group_permission('pkg1', 'foo', 'write', True)
        transaction.commit()
        self.db.add(g)
        self.assertEqual(len(g.permissions), 1)
        perm = g.permissions[0]
        self.assertEqual(perm.package, 'pkg1')
        self.assertFalse(perm.read)
        self.assertTrue(perm.write)

    def test_grant_group_bad_permission(self):
        """ Attempting to grant a bad permission raises ValueError """
        g = Group('foo')
        self.db.add(g)
        transaction.commit()
        with self.assertRaises(ValueError):
            self.access.edit_group_permission('pkg1', 'foo', 'wiggle', True)

    def test_revoke_group_permission(self):
        """ Can revoke group permissions on a package """
        g = Group('foo')
        perm = GroupPermission('pkg1', 'foo', read=True)
        self.db.add_all([g, perm])
        transaction.commit()
        self.access.edit_group_permission('pkg1', 'foo', 'read', False)
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
        user1 = make_user('user1', 'user1', True)
        user2 = make_user('user2', 'user2', False)
        user3 = make_user('user3', 'user3', False)
        user3.admin = True
        self.db.add_all([user1, user2, user3])
        transaction.commit()
        self.access.set_allow_register(False)
        self.access.create_group('g1')
        self.access.create_group('g2')
        self.access.edit_user_group('user2', 'g1', True)
        self.access.edit_user_group('user2', 'g2', True)
        self.access.edit_user_group('user3', 'g2', True)
        self.access.edit_user_permission('pkg1', 'user2', 'read', True)
        self.access.edit_user_permission('pkg2', 'user3', 'read', True)
        self.access.edit_user_permission('pkg2', 'user3', 'write', True)
        self.access.edit_group_permission('pkg1', 'g1', 'read', True)
        self.access.edit_group_permission('pkg2', 'g2', 'read', True)
        self.access.edit_group_permission('pkg2', 'g2', 'write', True)

        data = self.access.dump()

        self.assertFalse(data['allow_register'])

        # users
        self.assertEqual(len(data['users']), 2)
        for user in data['users']:
            self.assertTrue(pwd_context.verify(user['username'],
                                               user['password']))
            self.assertFalse(user['admin'] ^ (user['username'] == 'user3'))

        # pending users
        self.assertEqual(len(data['pending_users']), 1)
        user = data['pending_users'][0]
        self.assertTrue(pwd_context.verify(user['username'], user['password']))

        # groups
        self.assertEqual(len(data['groups']), 2)
        self.assertItemsEqual(data['groups']['g1'], ['user2'])
        self.assertItemsEqual(data['groups']['g2'], ['user2', 'user3'])

        # user package perms
        self.assertEqual(data['packages']['users'], {
            'pkg1': {
                'user2': ['read'],
            },
            'pkg2': {
                'user3': ['read', 'write'],
            },
        })

        # group package perms
        self.assertEqual(data['packages']['groups'], {
            'pkg1': {
                'g1': ['read'],
            },
            'pkg2': {
                'g2': ['read', 'write'],
            },
        })

    def test_load(self):
        """ Access control can load universal format data """
        user1 = make_user('user1', 'user1', True)
        user2 = make_user('user2', 'user2', False)
        user3 = make_user('user3', 'user3', False)
        user3.admin = True
        self.db.add_all([user1, user2, user3])
        transaction.commit()
        self.access.set_allow_register(False)
        self.access.create_group('g1')
        self.access.create_group('g2')
        self.access.edit_user_group('user2', 'g1', True)
        self.access.edit_user_group('user2', 'g2', True)
        self.access.edit_user_group('user3', 'g2', True)
        self.access.edit_user_permission('pkg1', 'user2', 'read', True)
        self.access.edit_user_permission('pkg2', 'user3', 'read', True)
        self.access.edit_user_permission('pkg2', 'user3', 'write', True)
        self.access.edit_group_permission('pkg1', 'g1', 'read', True)
        self.access.edit_group_permission('pkg2', 'g2', 'read', True)
        self.access.edit_group_permission('pkg2', 'g2', 'write', True)
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
                for key, val in obj1.iteritems():
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
        username, passw = 'foo™', 'bar™'
        self.access.register(username, passw)
        transaction.commit()
        user = self.db.query(User).first()
        self.assertEqual(user.username, username)
        self.assertTrue(pwd_context.verify(passw, user.password))


class TestMySQLBackend(TestSQLiteBackend):
    """ Test the SQLAlchemy access backend on a MySQL DB """

    DB_URL = 'mysql://root@127.0.0.1:3306/test?charset=utf8mb4'


class TestPostgresBackend(TestSQLiteBackend):
    """ Test the SQLAlchemy access backend on a Postgres DB """

    DB_URL = 'postgresql://postgres@127.0.0.1:5432/postgres'
