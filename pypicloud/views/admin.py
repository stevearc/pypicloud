""" API endpoints for admin controls """
import gzip
import json
from io import BytesIO

from paste.httpheaders import CONTENT_DISPOSITION  # pylint: disable=E0611
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.response import FileIter
from pyramid.view import view_config, view_defaults
from pyramid_duh import argify

from pypicloud.route import AdminResource


@view_defaults(context=AdminResource, subpath=(), permission="admin", renderer="json")
class AdminEndpoints(object):

    """ Collection of admin endpoints """

    def __init__(self, request):
        self.request = request

    @view_config(name="rebuild")
    def rebuild_package_list(self):
        """ Rebuild the package cache in the database """
        self.request.db.reload_from_storage()
        return self.request.response

    @view_config(name="pending_users", request_method="GET")
    def get_pending_users(self):
        """ Get the list of pending users """
        return self.request.access.pending_users()

    @view_config(name="user", request_method="GET")
    def get_users(self):
        """ Get the list of users """
        return self.request.access.user_data()

    @view_config(name="user", subpath=("username/*"), request_method="GET")
    def get_user(self):
        """ Get a single user """
        username = self.request.named_subpaths["username"]
        return self.request.access.user_data(username)

    @view_config(name="user", subpath=("username/*"), request_method="PUT")
    @argify
    def create_user(self, password):
        """ Create a new user """
        username = self.request.named_subpaths["username"]
        self.request.access.register(username, password)
        self.request.access.approve_user(username)
        return self.request.response

    @view_config(name="user", subpath=("username/*"), request_method="DELETE")
    def delete_user(self):
        """ Delete a user """
        username = self.request.named_subpaths["username"]
        self.request.access.delete_user(username)
        return self.request.response

    @view_config(name="user", subpath=("username/*", "approve"), request_method="POST")
    def approve_user(self):
        """ Approve a pending user """
        username = self.request.named_subpaths["username"]
        self.request.access.approve_user(username)
        return self.request.response

    @view_config(name="user", subpath=("username/*", "admin"), request_method="POST")
    @argify
    def set_admin_status(self, admin):
        """ Set a user to be or not to be an admin """
        username = self.request.named_subpaths["username"]
        self.request.access.set_user_admin(username, admin)
        return self.request.response

    @view_config(
        name="user", subpath=("username/*", "group", "group/*"), request_method="PUT"
    )
    @view_config(
        name="user", subpath=("username/*", "group", "group/*"), request_method="DELETE"
    )
    def mutate_group_member(self):
        """ Add a user to a group """
        username = self.request.named_subpaths["username"]
        group = self.request.named_subpaths["group"]
        self.request.access.edit_user_group(
            username, group, self.request.method == "PUT"
        )
        return self.request.response

    @view_config(name="group", request_method="GET")
    def get_groups(self):
        """ Get the list of groups """
        return self.request.access.groups()

    @view_config(name="group", subpath=("group/*"), request_method="PUT")
    def create_group(self):
        """ Create a group """
        group = self.request.named_subpaths["group"]
        if group in ("everyone", "authenticated"):
            return HTTPBadRequest("'%s' is a reserved name" % group)
        self.request.access.create_group(group)
        return self.request.response

    @view_config(name="group", subpath=("group/*"), request_method="DELETE")
    def delete_group(self):
        """ Delete a group """
        group = self.request.named_subpaths["group"]
        self.request.access.delete_group(group)
        return self.request.response

    @view_config(name="user", subpath=("username/*", "permissions"))
    def get_user_permissions(self):
        """ Get the package permissions for a user """
        username = self.request.named_subpaths["username"]
        return self.request.access.user_package_permissions(username)

    @view_config(name="group", subpath=("group/*"))
    def get_group(self):
        """ Get the members and package permissions for a group """
        group = self.request.named_subpaths["group"]
        return {
            "members": self.request.access.group_members(group),
            "packages": self.request.access.group_package_permissions(group),
        }

    @view_config(name="package", subpath=("package/*"), request_method="GET")
    def get_package_permissions(self):
        """ Get the user and group permissions set on a package """
        package = self.request.named_subpaths["package"]
        user_perms = [
            {"username": key, "permissions": val}
            for key, val in self.request.access.user_permissions(package).items()
        ]
        group_perms = [
            {"group": key, "permissions": val}
            for key, val in self.request.access.group_permissions(package).items()
        ]
        return {"user": user_perms, "group": group_perms}

    @view_config(
        name="package",
        subpath=("package/*", "type/user|group/r", "name/*", "permission/read|write/r"),
        request_method="PUT",
    )
    @view_config(
        name="package",
        subpath=("package/*", "type/user|group/r", "name/*", "permission/read|write/r"),
        request_method="DELETE",
    )
    def edit_permission(self):
        """ Edit user permission on a package """
        package = self.request.named_subpaths["package"]
        name = self.request.named_subpaths["name"]
        permission = self.request.named_subpaths["permission"]
        owner_type = self.request.named_subpaths["type"]
        if owner_type == "user":
            self.request.access.edit_user_permission(
                package, name, permission, self.request.method == "PUT"
            )
        else:
            self.request.access.edit_group_permission(
                package, name, permission, self.request.method == "PUT"
            )
        return self.request.response

    @view_config(name="register", request_method="POST")
    @argify
    def toggle_allow_register(self, allow):
        """ Allow or disallow user registration """
        self.request.access.set_allow_register(allow)
        return self.request.response

    @view_config(name="token", subpath=("username/*"), request_method="GET")
    def generate_token(self):
        """ Create a signup token for a user """
        username = self.request.named_subpaths["username"]
        token = self.request.access.get_signup_token(username)
        token_url = self.request.app_url("login") + "#/?token=" + token
        return {"token": token, "token_url": token_url}

    @view_config(name="acl.json.gz", request_method="GET")
    def download_access_control(self):
        """ Download the ACL data as a gzipped-json file """
        data = self.request.access.dump()
        compressed = BytesIO()
        zipfile = gzip.GzipFile(mode="wb", fileobj=compressed)
        zipfile.write(json.dumps(data, separators=(",", ":")).encode("utf8"))
        zipfile.close()
        compressed.seek(0)

        disp = CONTENT_DISPOSITION.tuples(filename="acl.json.gz")
        self.request.response.headers.update(disp)
        self.request.response.app_iter = FileIter(compressed)
        return self.request.response
