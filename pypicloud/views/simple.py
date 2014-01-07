""" Views for simple pip interaction """
from pypicloud.models import Package
from pypicloud.route import Root, SimplePackageResource, SimpleResource
from pyramid.httpexceptions import HTTPBadRequest, HTTPFound, HTTPForbidden
from pyramid.view import view_config

from pypicloud import api
from pyramid_duh import argify, addslash


@view_config(context=Root, request_method='POST', subpath=(),
             permission='login', renderer='json')
@view_config(context=SimpleResource, request_method='POST', subpath=(),
             permission='login', renderer='json')
@argify
def upload(request, name, version, content):
    """ Handle update commands """
    action = request.param(':action')
    name = Package.normalize_name(name)
    if action == 'file_upload':
        if not request.has_permission(name, 'w'):
            raise HTTPForbidden()
        return api.upload_package(request, name, version, content)
    else:
        raise HTTPBadRequest("Unknown action '%s'" % action)


@view_config(context=SimpleResource, request_method='GET', subpath=(),
             renderer='simple.jinja2')
@addslash
def simple(request):
    """ Render the list of all unique package names """
    names = api.list_packages(request)
    return {'pkgs': names}


@view_config(context=SimplePackageResource, request_method='GET', subpath=(),
             renderer='package.jinja2')
@addslash
def package_versions(context, request):
    """ Render the links for all versions of a package """
    name = Package.normalize_name(context.name)

    pkgs = Package.all(request, name)
    if request.registry.use_fallback and not pkgs:
        redirect_url = "%s/%s/" % (
            request.registry.fallback_url.rstrip('/'), name)
        return HTTPFound(location=redirect_url)
    if not request.has_permission(name, 'r'):
        raise HTTPForbidden()
    return {'pkgs': pkgs}
