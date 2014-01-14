""" API endpoints for admin controls """
from pypicloud.route import AdminResource
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.view import view_config

from pyramid_duh import argify


@view_config(context=AdminResource, name='rebuild', subpath=(),
             permission='admin')
def rebuild_package_list(request):
    """ Rebuild the package cache in the database """
    request.db.reload_from_storage()
    return request.response


@view_config(context=AdminResource, name='pending_users', subpath=(),
             request_method='GET', permission='admin', renderer='json')
def get_pending_users(request):
    """ Get the list of pending users """
    return request.access.pending_users()


@view_config(context=AdminResource, name='user', subpath=(),
             request_method='GET', permission='admin', renderer='json')
def get_users(request):
    """ Get the list of users """
    return request.access.user_data()


@view_config(context=AdminResource, name='user', subpath=('username/*'),
             request_method='GET', permission='admin', renderer='json')
def get_user(request):
    """ Get a single user """
    username = request.named_subpaths['username']
    return request.access.user_data(username)


@view_config(context=AdminResource, name='user', subpath=('username/*'),
             request_method='DELETE', permission='admin', renderer='json')
def delete_users(request):
    """ Delete a user """
    username = request.named_subpaths['username']
    request.access.delete_user(username)
    return request.response


@view_config(context=AdminResource, name='user', request_method='POST',
             subpath=('username/*', 'approve'), permission='admin',
             renderer='json')
def approve_user(request):
    """ Approve a pending user """
    username = request.named_subpaths['username']
    request.access.approve_user(username)
    return request.response


@view_config(context=AdminResource, name='user', request_method='POST',
             subpath=('username/*', 'admin'), permission='admin',
             renderer='json')
@argify
def set_admin_status(request, admin):
    """ Approve a pending user """
    username = request.named_subpaths['username']
    request.access.set_user_admin(username, admin)
    return request.response


@view_config(context=AdminResource, name='user', request_method='PUT',
             subpath=('username/*', 'group', 'group/*'), permission='admin',
             renderer='json')
def add_user_to_group(request):
    """ Add a user to a group """
    username = request.named_subpaths['username']
    group = request.named_subpaths['group']
    request.access.edit_user_group(username, group, True)
    return request.response


@view_config(context=AdminResource, name='user', request_method='DELETE',
             subpath=('username/*', 'group', 'group/*'), permission='admin',
             renderer='json')
def remove_user_from_group(request):
    """ Remove a user from a group """
    username = request.named_subpaths['username']
    group = request.named_subpaths['group']
    request.access.edit_user_group(username, group, False)
    return request.response


@view_config(context=AdminResource, name='group', subpath=(),
             request_method='GET', permission='admin', renderer='json')
def get_groups(request):
    """ Get the list of groups """
    return request.access.groups()


@view_config(context=AdminResource, name='group', subpath=('group/*'),
             request_method='DELETE', permission='admin', renderer='json')
def delete_group(request):
    """ Delete a group """
    group = request.named_subpaths['group']
    request.access.delete_group(group)
    return request.response


@view_config(context=AdminResource, name='user',
             subpath=('username/*', 'permissions'),
             permission='admin', renderer='json')
def get_user_permissions(request):
    """ Get the package permissions for a user """
    username = request.named_subpaths['username']
    return request.access.user_package_permissions(username)


@view_config(context=AdminResource, name='group', subpath=('group/*'),
             permission='admin', renderer='json')
def get_group_permissions(request):
    """ Get the package permissions for a group """
    group = request.named_subpaths['group']
    return {
        'members': request.access.group_members(group),
        'packages': request.access.group_package_permissions(group),
    }


@view_config(context=AdminResource, name='package', subpath=('package/*'),
             permission='admin', renderer='json')
def get_package_permissions(request):
    """ Get the user and group permissions set on a package """
    package = request.named_subpaths['package']
    user_perms = [{'username': key, 'permissions': val} for key, val in
                  request.access.user_permissions(package).iteritems()]
    group_perms = [{'group': key, 'permissions': val} for key, val in
                   request.access.group_permissions(package).iteritems()]
    return {
        'user': user_perms,
        'group': group_perms,
    }


@view_config(context=AdminResource, name='group', subpath=('group/*'),
             request_method='PUT', permission='admin')
def create_group(request):
    """ Create a group """
    group = request.named_subpaths['group']
    if group in ('everyone', 'authenticated'):
        raise HTTPBadRequest("'%s' is a reserved name" % group)
    request.access.create_group(group)
    return request.response


@view_config(context=AdminResource, name='package',
             subpath=('package/*', 'type/user|group/r',
                      'name/*', 'permission/read|write/r'),
             request_method='PUT', permission='admin')
@view_config(context=AdminResource, name='package',
             subpath=('package/*', 'type/user|group/r',
                      'name/*', 'permission/read|write/r'),
             request_method='DELETE', permission='admin')
def edit_permission(request):
    """ Edit user permission on a package """
    package = request.named_subpaths['package']
    name = request.named_subpaths['name']
    permission = request.named_subpaths['permission']
    owner_type = request.named_subpaths['type']
    if owner_type == 'user':
        request.access.edit_user_permission(package, name, permission,
                                            request.method == 'PUT')
    else:
        request.access.edit_group_permission(package, name, permission,
                                             request.method == 'PUT')
    return request.response


@view_config(context=AdminResource, name='register', subpath=(),
             request_method='POST', permission='admin')
@argify
def toggle_allow_register(request, allow):
    """ Allow or disallow user registration """
    request.access.set_allow_register(allow)
    return request.response
