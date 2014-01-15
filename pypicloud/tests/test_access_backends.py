""" Tests for access backends """
import transaction
from mock import MagicMock, patch
from pypicloud.access import (IAccessBackend, ConfigAccessBackend,
                              RemoteAccessBackend)
from pypicloud.access.sql import (SQLAccessBackend, User, UserPermission,
                                  association_table, GroupPermission, Group)
from pypicloud.route import Root
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.security import Everyone, Authenticated
from pyramid.testing import DummyRequest


try:
    import unittest2 as unittest  # pylint: disable=F0401
except ImportError:
    import unittest


class BaseACLTest(unittest.TestCase):

    """ Base test for anything checking ACLs """

    def setUp(self):
        self.request = DummyRequest()
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


class TestConfigBackend(BaseACLTest):

    """ Tests for access backend that uses config settings """

    def setUp(self):
        super(TestConfigBackend, self).setUp()
        self.backend = ConfigAccessBackend(self.request)
        self.request.access = self.backend

    def test_build_group(self):
        """ Group specifications create user map to groups """
        settings = {
            'group.g1': 'u1 u2 u3',
            'group.g2': 'u2 u3 u4',
            'unrelated': 'weeeeee',
        }
        self.backend.configure(settings)
        self.assertItemsEqual(self.backend.groups(), ['g1', 'g2'])
        self.assertItemsEqual(self.backend.groups('u1'), ['g1'])
        self.assertItemsEqual(self.backend.groups('u2'), ['g1', 'g2'])
        self.assertItemsEqual(self.backend.groups('u3'), ['g1', 'g2'])
        self.assertItemsEqual(self.backend.groups('u4'), ['g2'])

    def test_group_members(self):
        """ Fetch all members of a group """
        settings = {
            'group.g1': 'u1 u2 u3',
        }
        self.backend.configure(settings)
        self.assertItemsEqual(self.backend.group_members('g1'),
                              ['u1', 'u2', 'u3'])

    def test_all_group_permissions(self):
        """ Fetch all group permissions on a package """
        settings = {
            'package.mypkg.group.g1': 'r',
            'package.mypkg.group.g2': 'rw',
        }
        self.backend.configure(settings)
        perms = self.backend.group_permissions('mypkg')
        self.assertEqual(perms, {'g1': ['read'], 'g2': ['read', 'write']})

    def test_group_permissions(self):
        """ Fetch permissions for a single group on a package """
        settings = {
            'package.mypkg.group.g1': 'r',
            'package.mypkg.group.g2': 'rw',
        }
        self.backend.configure(settings)
        perms = self.backend.group_permissions('mypkg', 'g1')
        self.assertEqual(perms, ['read'])

    def test_everyone_permission(self):
        """ All users have 'everyone' permissions """
        settings = {'package.mypkg.group.everyone': 'r'}
        self.backend.configure(settings)
        perms = self.backend.principal_permissions('mypkg', Everyone)
        self.assertEqual(perms, ['read'])

    def test_authenticated_permission(self):
        """ All logged-in users have 'authenticated' permissions """
        settings = {'package.mypkg.group.authenticated': 'r'}
        self.backend.configure(settings)
        perms = self.backend.principal_permissions('mypkg', Authenticated)
        self.assertEqual(perms, ['read'])

    def test_all_user_perms(self):
        """ Fetch permissions on a package for all users """
        settings = {
            'package.mypkg.user.u1': 'r',
            'package.mypkg.user.u2': 'rw',
        }
        self.backend.configure(settings)
        perms = self.backend.user_permissions('mypkg')
        self.assertEqual(perms, {'u1': ['read'], 'u2': ['read', 'write']})

    def test_user_perms(self):
        """ Fetch permissions on a package for one user """
        settings = {
            'package.mypkg.user.u1': 'r',
            'package.mypkg.user.u2': 'rw',
        }
        self.backend.configure(settings)
        perms = self.backend.user_permissions('mypkg', 'u1')
        self.assertEqual(perms, ['read'])

    def test_user_package_perms(self):
        """ Fetch all packages a user has permissions on """
        settings = {
            'package.pkg1.user.u1': 'r',
            'package.pkg2.user.u1': 'rw',
        }
        self.backend.configure(settings)
        packages = self.backend.user_package_permissions('u1')
        self.assertItemsEqual(packages, [
            {'package': 'pkg1', 'permissions': ['read']},
            {'package': 'pkg2', 'permissions': ['read', 'write']},
        ])

    def test_group_package_perms(self):
        """ Fetch all packages a group has permissions on """
        settings = {
            'package.pkg1.group.g1': 'r',
            'package.pkg2.group.g1': 'rw',
        }
        self.backend.configure(settings)
        packages = self.backend.group_package_permissions('g1')
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
        self.backend.configure(settings)
        users = self.backend.user_data()
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
        self.backend.configure(settings)
        user = self.backend.user_data('foo')
        self.assertEqual(user, {
            'username': 'foo',
            'admin': True,
            'groups': ['foobars'],
        })

    def test_zero_security(self):
        """ In zero_security_mode everyone has 'r' permission """
        settings = {
            'auth.zero_security_mode': True
        }
        self.backend.configure(settings)
        can_read = self.backend.has_permission('floobydooby', 'read')
        self.assertTrue(can_read)

    def test_zero_security_write(self):
        """ zero_security_mode has no impact on 'w' permission """
        settings = {
            'auth.zero_security_mode': True
        }
        self.backend.configure(settings)
        perms = self.backend.principal_permissions('pkg', Everyone)
        self.assertEqual(perms, ['read'])

    def test_root_acl_zero_sec(self):
        """ Root ACL is super permissive in zero security mode """
        settings = {
            'auth.zero_security_mode': True
        }
        self.backend.configure(settings)
        root = Root(self.request)
        self.assert_allowed(root, 'login', ['admin', Everyone])
        self.assert_allowed(root, 'read', ['admin', Everyone])
        self.assert_allowed(root, 'write', ['admin', Authenticated])

    def test_zero_security_mode_acl(self):
        """ Zero security mode means ACL is empty """
        settings = {
            'auth.zero_security_mode': True
        }
        self.backend.configure(settings)
        acl = self.backend.get_acl('mypkg')
        self.assertEqual(acl, [])

    def test_need_admin(self):
        """ Config backend is static and never needs admin """
        self.backend.configure({})
        self.assertFalse(self.backend.need_admin())


class TestRemoteBackend(unittest.TestCase):

    """ Tests for the access backend that delegates calls to remote server """

    def setUp(self):
        request = DummyRequest()
        self.backend = RemoteAccessBackend(request)
        self.auth = ('user', 'pass')
        settings = {
            'auth.backend_server': 'server',
            'auth.user': self.auth[0],
            'auth.password': self.auth[1],
        }
        self.backend.configure(settings)
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
        self.requests.get.assert_called_with('server/group_package_permissions',
                                             params=params, auth=self.auth)
        self.assertEqual(groups, self.requests.get().json())


class TestSQLBackend(unittest.TestCase):

    """ Tests for the SQL access backend """
    @classmethod
    def setUpClass(cls):
        super(TestSQLBackend, cls).setUpClass()
        settings = {
            'auth.db.url': 'sqlite:///:memory:',
        }
        SQLAccessBackend.configure(settings)

    def setUp(self):
        super(TestSQLBackend, self).setUp()
        self.db = SQLAccessBackend.dbmaker()
        self.access = SQLAccessBackend(MagicMock())

    def tearDown(self):
        super(TestSQLBackend, self).tearDown()
        transaction.abort()
        self.db.query(User).delete()
        self.db.query(UserPermission).delete()
        self.db.query(GroupPermission).delete()
        self.db.query(Group).delete()
        self.db.execute(association_table.delete())  # pylint: disable=E1120
        transaction.commit()
        self.access.db.close()
        self.db.close()

    def test_verify(self):
        """ Verify login credentials against database """
        user = User('foo', 'bar', False)
        self.db.add(user)
        transaction.commit()
        valid = self.access.verify_user('foo', 'bar')
        self.assertTrue(valid)

        valid = self.access.verify_user('foo', 'barrrr')
        self.assertFalse(valid)

    def test_verify_pending(self):
        """ Pending users fail to verify """
        user = User('foo', 'bar')
        self.db.add(user)
        transaction.commit()
        valid = self.access.verify_user('foo', 'bar')
        self.assertFalse(valid)

    def test_admin(self):
        """ Retrieve admin status from database """
        user = User('foo', 'bar', False)
        user.admin = True
        self.db.add(user)
        transaction.commit()
        is_admin = self.access.is_admin('foo')
        self.assertTrue(is_admin)

    def test_admin_default_false(self):
        """ The default admin status is False """
        user = User('foo', 'bar', False)
        self.db.add(user)
        transaction.commit()
        is_admin = self.access.is_admin('foo')
        self.assertFalse(is_admin)

    def test_user_groups(self):
        """ Retrieve a user's groups from database """
        user = User('foo', 'bar', False)
        g1 = Group('brotatos')
        g2 = Group('sharkfest')
        user.groups.update([g1, g2])
        self.db.add_all([user, g1, g2])
        transaction.commit()
        groups = self.access.groups('foo')
        self.assertItemsEqual(groups, ['brotatos', 'sharkfest'])

    def test_groups(self):
        """ Retrieve all groups from database """
        user = User('foo', 'bar', False)
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
        u1 = User('u1', 'bar', False)
        u2 = User('u2', 'bar', False)
        u3 = User('u3', 'bar', False)
        g1 = Group('g1')
        g1.users.update([u1, u2])
        self.db.add_all([u1, u2, u3, g1])
        transaction.commit()
        users = self.access.group_members('g1')
        self.assertItemsEqual(users, ['u1', 'u2'])

    def test_all_user_permissions(self):
        """ Retrieve all user permissions on package from database """
        user = User('foo', 'bar', False)
        user2 = User('foo2', 'bar', False)
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
        user = User('foo', 'bar', False)
        user2 = User('foo2', 'bar', False)
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
        user = User('foo', 'bar', False)
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
        u1 = User('foo', 'bar', False)
        u1.admin = True
        u2 = User('bar', 'bar', False)
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
        u1 = User('foo', 'bar', False)
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
        user = User('foo', 'bar', False)
        user.admin = True
        self.db.add(user)
        transaction.commit()
        self.assertFalse(self.access.need_admin())

    def test_need_admin(self):
        """ If admin doesn't exist, need an admin """
        user = User('foo', 'bar', False)
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

    def test_pending(self):
        """ Registering a user puts them in pending list """
        user = User('foo', 'bar')
        self.db.add(user)
        transaction.commit()
        users = self.access.pending_users()
        self.assertEqual(users, ['foo'])

    def test_pending_not_in_users(self):
        """ Pending users are not listed in all_users """
        user = User('foo', 'bar')
        self.db.add(user)
        transaction.commit()
        users = self.access.user_data()
        self.assertEqual(users, [])

    def test_approve(self):
        """ Approving user marks them as not pending """
        user = User('foo', 'bar')
        self.db.add(user)
        transaction.commit()
        self.access.approve_user('foo')
        transaction.commit()
        user = self.db.query(User).first()
        self.assertFalse(user.pending)

    def test_edit_password(self):
        """ Users can edit their passwords """
        user = User('foo', 'bar', False)
        self.db.add(user)
        transaction.commit()
        self.access.edit_user_password('foo', 'baz')
        transaction.commit()
        user = self.db.query(User).first()
        self.assertTrue(user.verify('baz'))

    def test_delete_user(self):
        """ Can delete users """
        user = User('foo', 'bar', False)
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
        user = User('foo', 'bar', False)
        self.db.add(user)
        transaction.commit()
        self.access.set_user_admin('foo', True)
        transaction.commit()
        self.db.add(user)
        self.assertTrue(user.admin)

    def test_remove_admin(self):
        """ Can demote an admin to normal user """
        user = User('foo', 'bar', False)
        user.admin = True
        self.db.add(user)
        transaction.commit()
        self.access.set_user_admin('foo', False)
        transaction.commit()
        self.db.add(user)
        self.assertFalse(user.admin)

    def test_add_user_to_group(self):
        """ Can add a user to a group """
        user = User('foo', 'bar', False)
        group = Group('g1')
        self.db.add_all([user, group])
        transaction.commit()
        self.access.edit_user_group('foo', 'g1', True)
        transaction.commit()
        self.db.add(user)
        self.assertEqual([g.name for g in user.groups], ['g1'])

    def test_remove_user_from_group(self):
        """ Can remove a user from a group """
        user = User('foo', 'bar', False)
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
        user = User('foo', 'bar')
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

    def test_grant_user_permission(self):
        """ Can give users permissions on a package """
        user = User('foo', 'bar', False)
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

    def test_revoke_user_permission(self):
        """ Can revoke user permissions on a package """
        user = User('foo', 'bar', False)
        perm = UserPermission('pkg1', 'foo', read=True)
        self.db.add_all([user, perm])
        transaction.commit()
        self.access.edit_user_permission('pkg1', 'foo', 'read', False)
        transaction.commit()
        self.db.add(user)
        self.assertEqual(len(user.permissions), 0)

    def test_grant_group_permission(self):
        """ Can give groups permissions on a package """
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
