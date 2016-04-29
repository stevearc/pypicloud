""" Views for simple pip interaction """
import posixpath

import logging
import six
from pyramid.httpexceptions import HTTPBadRequest, HTTPFound, HTTPNotFound
from pyramid.view import view_config
from pyramid_duh import argify, addslash

from pypicloud.route import Root, SimplePackageResource, SimpleResource
from pypicloud.util import normalize_name, parse_filename


LOG = logging.getLogger(__name__)


@view_config(context=Root, request_method='POST', subpath=(), renderer='json')
@view_config(context=SimpleResource, request_method='POST', subpath=(),
             renderer='json')
@argify
def upload(request, content, name=None, version=None):
    """ Handle update commands """
    action = request.param(':action', 'file_upload')
    # Direct uploads from the web UI go here, and don't have a name/version
    if name is None or version is None:
        name, version = parse_filename(content.filename)
    else:
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
    fallback = request.registry.fallback
    if fallback == 'redirect':
        if request.registry.always_show_upstream:
            return _simple_redirect_always_show(context, request)
        else:
            return _simple_redirect(context, request)
    elif fallback == 'cache':
        if request.registry.always_show_upstream:
            return _simple_cache_always_show(context, request)
        else:
            return _simple_cache(context, request)
    else:
        return _simple_serve(context, request)


def get_fallback_packages(request, package_name, redirect=True):
    """ Get all package versions for a package from the fallback_url """
    dists = request.locator.get_project(package_name)
    pkgs = {}
    for version, url_set in six.iteritems(dists.get('urls', {})):
        dist = dists[version]
        for url in url_set:
            filename = posixpath.basename(url)
            if not redirect:
                url = request.app_url('api', 'package', dist.name, filename)
            pkgs[filename] = url
    return pkgs


def packages_to_dict(request, packages):
    """ Convert a list of packages to a dict used by the template """
    pkgs = {}
    for package in packages:
        pkgs[package.filename] = package.get_url(request)
    return pkgs


def _pkg_response(pkgs):
    """ Take a package mapping and return either a dict for jinja or a 404 """
    if pkgs:
        return {'pkgs': pkgs}
    else:
        return HTTPNotFound("No packages found")


def _redirect(context, request):
    """ Return a 302 to the fallback url for this package """
    redirect_url = "%s/%s/" % (
        request.registry.fallback_url.rstrip('/'), context.name)
    return HTTPFound(location=redirect_url)


def _simple_redirect(context, request):
    """ Service /simple with fallback=redirect """
    normalized_name = normalize_name(context.name)
    packages = request.db.all(normalized_name)
    if packages:
        if not request.access.has_permission(normalized_name, 'read'):
            if request.is_logged_in:
                return _redirect(context, request)
            else:
                return request.request_login()
        else:
            return _pkg_response(packages_to_dict(request, packages))
    else:
        return _redirect(context, request)


def _simple_redirect_always_show(context, request):
    """ Service /simple with fallback=redirect """
    normalized_name = normalize_name(context.name)
    packages = request.db.all(normalized_name)
    if packages:
        if not request.access.has_permission(normalized_name, 'read'):
            if request.is_logged_in:
                return _redirect(context, request)
            else:
                return request.request_login()
        else:
            pkgs = get_fallback_packages(request, context.name)
            stored_pkgs = packages_to_dict(request, packages)
            # Overwrite existing package urls
            for filename, url in six.iteritems(stored_pkgs):
                pkgs[filename] = url
            return _pkg_response(pkgs)
    else:
        return _redirect(context, request)


def _simple_cache(context, request):
    """ Service /simple with fallback=cache """
    normalized_name = normalize_name(context.name)

    if not request.access.has_permission(normalized_name, 'read'):
        if request.is_logged_in:
            return HTTPNotFound("No packages found named %r" % normalized_name)
        else:
            return request.request_login()

    packages = request.db.all(normalized_name)
    if packages:
        return _pkg_response(packages_to_dict(request, packages))

    if not request.access.can_update_cache():
        if request.is_logged_in:
            return HTTPNotFound("No packages found named %r" % normalized_name)
        else:
            return request.request_login()
    else:
        pkgs = get_fallback_packages(request, context.name, False)
        return _pkg_response(pkgs)


def _simple_cache_always_show(context, request):
    """ Service /simple with fallback=mirror """
    normalized_name = normalize_name(context.name)

    if not request.access.has_permission(normalized_name, 'read'):
        if request.is_logged_in:
            return _redirect(context, request)
        else:
            return request.request_login()

    packages = request.db.all(normalized_name)
    if packages:
        if not request.access.can_update_cache():
            if request.is_logged_in:
                pkgs = get_fallback_packages(request, context.name)
                stored_pkgs = packages_to_dict(request, packages)
                # Overwrite existing package urls
                for filename, url in six.iteritems(stored_pkgs):
                    pkgs[filename] = url
                return _pkg_response(pkgs)
            else:
                return request.request_login()
        else:
            pkgs = get_fallback_packages(request, context.name, False)
            stored_pkgs = packages_to_dict(request, packages)
            # Overwrite existing package urls
            for filename, url in six.iteritems(stored_pkgs):
                pkgs[filename] = url
            return _pkg_response(pkgs)
    else:
        if not request.access.can_update_cache():
            if request.is_logged_in:
                return _redirect(context, request)
            else:
                return request.request_login()
        else:
            pkgs = get_fallback_packages(request, context.name, False)
            return _pkg_response(pkgs)


def _simple_serve(context, request):
    """ Service /simple with fallback=none """
    normalized_name = normalize_name(context.name)

    if not request.access.has_permission(normalized_name, 'read'):
        if request.is_logged_in:
            return HTTPNotFound("No packages found named %r" % normalized_name)
        else:
            return request.request_login()

    packages = request.db.all(normalized_name)
    return _pkg_response(packages_to_dict(request, packages))
