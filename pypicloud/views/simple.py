""" Views for simple pip interaction """
import posixpath

import logging
import six
from pyramid.httpexceptions import HTTPBadRequest, HTTPFound, HTTPNotFound
from pyramid.view import view_config
from pyramid_duh import argify, addslash

from pypicloud.route import Root, SimplePackageResource, SimpleResource
from pypicloud.util import normalize_name


LOG = logging.getLogger(__name__)


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
    if not request.access.has_permission(normalized_name, 'read'):
        return request.forbid()
    fallback = request.registry.fallback
    can_update_cache = request.access.can_update_cache()

    packages = request.db.all(normalized_name)
    pkgs = {}
    if fallback == 'mirror':
        if can_update_cache:
            pkgs = get_fallback_packages(request, context.name)
        if packages:
            # Overwrite upstream urls with cached urls
            for package in packages:
                pkgs[package.filename] = package.get_url(request)
        if pkgs:
            return {'pkgs': pkgs}
        else:
            return HTTPNotFound("No packages found named %r" % normalized_name)
    elif packages:
        for package in packages:
            pkgs[package.filename] = package.get_url(request)
        return {'pkgs': pkgs}
    elif fallback == 'cache':
        if not can_update_cache:
            return request.forbid()
        pkgs = get_fallback_packages(request, context.name)
        if pkgs:
            return {'pkgs': pkgs}
        else:
            return HTTPNotFound("No packages found named %r" % normalized_name)
    elif fallback == 'redirect':
        redirect_url = "%s/%s/" % (
            request.registry.fallback_url.rstrip('/'), context.name)
        return HTTPFound(location=redirect_url)
    else:
        return HTTPNotFound()


def get_fallback_packages(request, package_name):
    """ Get all package versions for a package from the fallback_url """
    dists = request.locator.get_project(package_name)
    pkgs = {}
    for version, url_set in six.iteritems(dists.get('urls', {})):
        dist = dists[version]
        for url in url_set:
            filename = posixpath.basename(url)
            url = request.app_url('api', 'package', dist.name, filename)
            pkgs[filename] = url
    return pkgs
