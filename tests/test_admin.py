""" Tests for admin endpoints """
from mock import MagicMock
from pyramid.httpexceptions import HTTPBadRequest

from pypicloud.views.admin import AdminEndpoints

from . import MockServerTest


class TestAdmin(MockServerTest):

    """ Tests for admin endpoints """

    def setUp(self):
        super(TestAdmin, self).setUp()
        self.access = self.request.access = MagicMock()

    def test_rebuild(self):
        """ Rebuild endpoint refreshes db cache """
        self.request.db = MagicMock()
        AdminEndpoints(self.request).rebuild_package_list()
        self.assertTrue(self.request.db.reload_from_storage.called)

    def test_get_pending_users(self):
        """ Retrieve pending users from access backend """
        ret = AdminEndpoints(self.request).get_pending_users()
        self.assertEqual(ret, self.access.pending_users())

    def test_get_users(self):
        """ Retrieve all users from access backend """
        ret = AdminEndpoints(self.request).get_users()
        self.assertEqual(ret, self.access.user_data())

    def test_get_user(self):
        """ Retrieve data for a single user """
        self.request.named_subpaths = {"username": "a"}
        ret = AdminEndpoints(self.request).get_user()
        self.access.user_data.assert_called_with("a")
        self.assertEqual(ret, self.access.user_data())

    def test_delete_user(self):
        """ Delete user from access backend """
        self.request.named_subpaths = {"username": "a"}
        AdminEndpoints(self.request).delete_user()
        self.access.delete_user.assert_called_with("a")

    def test_approve_user(self):
        """ Approve a pending user """
        self.request.named_subpaths = {"username": "a"}
        AdminEndpoints(self.request).approve_user()
        self.access.approve_user.assert_called_with("a")

    def test_set_admin_status(self):
        """ Set the admin flag for a user """
        self.request.named_subpaths = {"username": "a"}
        AdminEndpoints(self.request).set_admin_status(True)
        self.access.set_user_admin.assert_called_with("a", True)

    def test_add_group_member(self):
        """ Add a user to a group """
        self.request.named_subpaths = {"username": "a", "group": "b"}
        self.request.method = "PUT"
        AdminEndpoints(self.request).mutate_group_member()
        self.access.edit_user_group.assert_called_with("a", "b", True)

    def test_remove_group_member(self):
        """ Remove a user from a group """
        self.request.named_subpaths = {"username": "a", "group": "b"}
        self.request.method = "DELETE"
        AdminEndpoints(self.request).mutate_group_member()
        self.access.edit_user_group.assert_called_with("a", "b", False)

    def test_get_groups(self):
        """ Retrieve list of all groups """
        ret = AdminEndpoints(self.request).get_groups()
        self.assertEqual(ret, self.access.groups())

    def test_delete_group(self):
        """ Delete a group """
        self.request.named_subpaths = {"group": "a"}
        AdminEndpoints(self.request).delete_group()
        self.access.delete_group.assert_called_with("a")

    def test_get_user_permissions(self):
        """ Get a user's permissions from the access backend """
        self.request.named_subpaths = {"username": "a"}
        ret = AdminEndpoints(self.request).get_user_permissions()
        self.access.user_package_permissions.assert_called_with("a")
        self.assertEqual(ret, self.access.user_package_permissions())

    def test_get_group(self):
        """ Get a group's members and permissions """
        self.request.named_subpaths = {"group": "a"}
        ret = AdminEndpoints(self.request).get_group()
        self.access.group_members.assert_called_with("a")
        self.access.group_package_permissions.assert_called_with("a")
        self.assertEqual(
            ret,
            {
                "members": self.access.group_members(),
                "packages": self.access.group_package_permissions(),
            },
        )

    def test_get_package_permissions(self):
        """ Get user and group permissions for a package """
        self.request.named_subpaths = {"package": "a"}
        self.access.user_permissions.return_value = {"u1": ["read"]}
        self.access.group_permissions.return_value = {"g1": ["read", "write"]}
        ret = AdminEndpoints(self.request).get_package_permissions()
        self.assertEqual(
            ret,
            {
                "user": [{"username": "u1", "permissions": ["read"]}],
                "group": [{"group": "g1", "permissions": ["read", "write"]}],
            },
        )

    def test_create_group(self):
        """ Create a group """
        self.request.named_subpaths = {"group": "a"}
        AdminEndpoints(self.request).create_group()
        self.access.create_group.assert_called_with("a")

    def test_no_create_everyone_group(self):
        """ Cannot create the 'everyone' group """
        self.request.named_subpaths = {"group": "everyone"}
        ret = AdminEndpoints(self.request).create_group()
        self.assertTrue(isinstance(ret, HTTPBadRequest))

    def test_no_create_authenticated_group(self):
        """ Cannot create the 'authenticated' group """
        self.request.named_subpaths = {"group": "authenticated"}
        ret = AdminEndpoints(self.request).create_group()
        self.assertTrue(isinstance(ret, HTTPBadRequest))

    def test_add_user_permission(self):
        """ Add a user permission to a package """
        self.request.named_subpaths = {
            "type": "user",
            "package": "p",
            "name": "u",
            "permission": "read",
        }
        self.request.method = "PUT"
        AdminEndpoints(self.request).edit_permission()
        self.access.edit_user_permission.assert_called_with("p", "u", "read", True)

    def test_remove_user_permission(self):
        """ Remove a user permission from a package """
        self.request.named_subpaths = {
            "type": "user",
            "package": "p",
            "name": "u",
            "permission": "read",
        }
        self.request.method = "DELETE"
        AdminEndpoints(self.request).edit_permission()
        self.access.edit_user_permission.assert_called_with("p", "u", "read", False)

    def test_add_group_permission(self):
        """ Add a group permission to a package """
        self.request.named_subpaths = {
            "type": "group",
            "package": "p",
            "name": "g",
            "permission": "read",
        }
        self.request.method = "PUT"
        AdminEndpoints(self.request).edit_permission()
        self.access.edit_group_permission.assert_called_with("p", "g", "read", True)

    def test_remove_group_permission(self):
        """ Remove a group permission from a package """
        self.request.named_subpaths = {
            "type": "group",
            "package": "p",
            "name": "g",
            "permission": "read",
        }
        self.request.method = "DELETE"
        AdminEndpoints(self.request).edit_permission()
        self.access.edit_group_permission.assert_called_with("p", "g", "read", False)

    def test_toggle_allow_register(self):
        """ Toggle registration enabled """
        AdminEndpoints(self.request).toggle_allow_register(True)
        self.access.set_allow_register.assert_called_with(True)
