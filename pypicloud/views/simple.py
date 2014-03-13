""" Views for simple pip interaction """
import six
from pyramid.httpexceptions import HTTPBadRequest, HTTPFound, HTTPNotFound
from pyramid.view import view_config

import posixpath
from pypicloud.route import Root, SimplePackageResource, SimpleResource
from pypicloud.util import normalize_name, FilenameScrapingLocator
from pyramid_duh import argify, addslash


@view_config(context=Root, request_method='POST', subpath=(), renderer='json')
@view_config(context=SimpleResource, request_method='POST', subpath=(),
             renderer='json')
@argify
def upload(request, name, version, content):
    """ Handle update commands """
    action = request.param(':action')
    name = normalize_name(name)
    if action == 'file_upload':
        if not request.access.has_permission(name, 'write'):
            return request.forbid()
        try:
            return request.db.upload(content.filename, content.file, name=name,
                                     version=version)
        except ValueError as e:
            return HTTPBadRequest(*e.args)
    else:
        return HTTPBadRequest("Unknown action '%s'" % action)


@view_config(context=SimpleResource, request_method='GET', subpath=(),
             renderer='simple.jinja2')
@addslash
def simple(request):
    """ Render the list of all unique package names """
    names = request.db.distinct()
    i = 0
    while i < len(names):
        name = names[i]
        if not request.access.has_permission(name, 'read'):
            del names[i]
            continue
        i += 1
    return {'pkgs': names}


@view_config(context=SimplePackageResource, request_method='GET', subpath=(),
             renderer='package.jinja2')
@addslash
def package_versions(context, request):
    """ Render the links for all versions of a package """
    normalized_name = normalize_name(context.name)

    packages = request.db.all(normalized_name)
    if packages:
        if not request.access.has_permission(normalized_name, 'read'):
            return request.forbid()
        pkgs = {}
        for package in packages:
            pkgs[package.filename] = package.get_url(request)
        return {'pkgs': pkgs}

    elif request.registry.fallback == 'cache':
        if not request.access.can_update_cache():
            return request.forbid()
        locator = FilenameScrapingLocator(request.registry.fallback_url)
        dists = locator.get_project(context.name)
        if not dists:
            return HTTPNotFound()
        pkgs = {}
        for dist in six.itervalues(dists):
            filename = posixpath.basename(dist.source_url)
            url = request.app_url('api', 'package', dist.name, filename)
            pkgs[filename] = url
        return {'pkgs': pkgs}
    elif request.registry.fallback == 'redirect':
        redirect_url = "%s/%s/" % (
            request.registry.fallback_url.rstrip('/'), context.name)
        return HTTPFound(location=redirect_url)
    else:
        return HTTPNotFound()
