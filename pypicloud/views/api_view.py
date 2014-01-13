""" Views for simple api calls that return json data """
from pyramid.httpexceptions import HTTPNotFound
from pypicloud.route import (APIResource, APIPackageResource,
                             APIPackagingResource, APIPackageVersionResource)
from pyramid.view import view_config

from pypicloud import api
from pyramid_duh import argify, addslash


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


@view_config(context=APIResource, name='rebuild', subpath=(),
             permission='admin')
def rebuild_package_list(request):
    """ Rebuild the package cache in the database """
    request.db.reload_from_storage()
    return request.response
