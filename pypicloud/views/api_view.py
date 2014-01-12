""" Views for simple api calls that return json data """
from pypicloud.models import Package
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
    versions = Package.all(request, context.name)
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
    api.delete_package(request, context.name, context.version)
    return request.response


@view_config(context=APIResource, name='rebuild', subpath=(),
             permission='admin')
def rebuild_package_list(request):
    """ Rebuild the package cache in the database """
    # TODO: (stevearc 2014-01-02) Technically could cause thundering herd
    # problem. Should fix that at some point.
    if request.dbtype == 'sql':
        request.db.query(Package).delete()
    elif request.dbtype == 'redis':
        keys = request.db.keys(Package.redis_prefix + '*')
        if keys:
            request.db.delete(*keys)

    Package.reload_from_s3(request)
    return request.response
