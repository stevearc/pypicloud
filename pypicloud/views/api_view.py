""" Views for simple api calls that return json data """
from pypicloud.route import (APIResource, APIPackageResource,
                             APIPackagingResource, APIPackageVersionResource)
from pyramid.httpexceptions import HTTPNotFound, HTTPForbidden
from pyramid.view import view_config

from pypicloud import api
from pyramid_duh import argify, addslash
from pyramid.security import NO_PERMISSION_REQUIRED, remember


@view_config(context=APIPackagingResource, request_method='GET',
             subpath=(), renderer='json')
@addslash
def all_packages(request):
    """ List all unique package names """
    names = api.list_packages(request)
    return {'packages': names}


@view_config(context=APIPackageResource, request_method='GET',
             subpath=(), renderer='json', permission='read')
@addslash
def package_versions(context, request):
    """ List all unique package names """
    versions = request.db.all(context.name)
    return {
        'packages': versions,
        'write': request.access.has_permission(context.name, 'write'),
    }


@view_config(context=APIPackageVersionResource, request_method='POST',
             subpath=(), renderer='json', permission='write')
@argify
def upload_package(context, request, content):
    """ Upload a package """
    return api.upload_package(request, context.name, context.version, content)


@view_config(context=APIPackageVersionResource, request_method='DELETE',
             subpath=(), permission='write')
def delete_package(context, request):
    """ Delete a package """
    package = request.db.fetch(context.name, context.version)
    if package is None:
        return HTTPNotFound("Could not find %s==%s" % (context.name,
                                                       context.version))
    request.db.delete(package)
    return request.response


@view_config(context=APIResource, name='user', request_method='PUT',
             subpath=('username/*'), renderer='json',
             permission=NO_PERMISSION_REQUIRED)
@argify
def register(request, password):
    """ Register a user """
    if not request.access.allow_register and not request.access.need_admin():
        raise HTTPNotFound()
    username = request.named_subpaths['username']
    request.access.register(username, password)
    if request.access.need_admin():
        request.access.approve_user(username)
        request.access.set_user_admin(username, True)
        request.response.headers.extend(remember(request, username))
    return request.response


@view_config(context=APIResource, name='user', subpath=('password'),
             request_method='POST', permission='login')
@argify
def change_password(request, old_password, new_password):
    """ Change a user's password """
    if not request.access.verify_user(request.userid, old_password):
        return HTTPForbidden()
    request.access.edit_user_password(request.userid, new_password)
    return request.response
