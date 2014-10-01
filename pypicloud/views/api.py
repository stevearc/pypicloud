""" Views for simple api calls that return json data """
import posixpath

import logging
from contextlib import closing
from paste.httpheaders import CONTENT_DISPOSITION
from pyramid.httpexceptions import HTTPNotFound, HTTPForbidden, HTTPBadRequest
from pyramid.security import NO_PERMISSION_REQUIRED, remember
from pyramid.view import view_config
from pyramid_duh import argify, addslash
from six import BytesIO
from six.moves.urllib.request import urlopen  # pylint: disable=F0401,E0611

from pypicloud.route import (APIResource, APIPackageResource,
                             APIPackagingResource, APIPackageFileResource)
from pypicloud.util import (normalize_name, BetterScrapingLocator,
                            FilenameScrapingLocator)


LOG = logging.getLogger(__name__)


@view_config(context=APIPackagingResource, request_method='GET',
             subpath=(), renderer='json')
@addslash
@argify
def all_packages(request, verbose=False):
    """ List all packages """
    if verbose:
        packages = request.db.summary()
    else:
        packages = request.db.distinct()
    i = 0
    while i < len(packages):
        package = packages[i]
        name = package if isinstance(package, basestring) else package['name']
        if not request.access.has_permission(name, 'read'):
            del packages[i]
            continue
        i += 1
    return {'packages': packages}


@view_config(context=APIPackageResource, request_method='GET',
             subpath=(), renderer='json', permission='read')
@addslash
def package_versions(context, request):
    """ List all unique package versions """
    normalized_name = normalize_name(context.name)
    versions = request.db.all(normalized_name)
    return {
        'packages': versions,
        'write': request.access.has_permission(normalized_name, 'write'),
    }


def fetch_dist(request, dist):
    """ Fetch a Distribution and upload it to the storage backend """
    filename = posixpath.basename(dist.source_url)
    with closing(urlopen(dist.source_url)) as url:
        data = url.read()
    return request.db.upload(filename, BytesIO(data), dist.name), data


@view_config(context=APIPackageFileResource, request_method='GET',
             permission='read')
def download_package(context, request):
    """ Download package, or redirect to the download link """
    package = request.db.fetch(context.filename)
    if not package:
        if request.registry.fallback != 'cache':
            return HTTPNotFound()
        if not request.access.can_update_cache():
            return request.forbid()
        # If we are caching pypi, download the package from pypi and save it
        locator = FilenameScrapingLocator(request.registry.fallback_url)
        dists = locator.get_project(context.name)
        dist = dists.get(context.filename)
        if dist is None:
            return HTTPNotFound()
        LOG.info("Caching %s from %s", context.filename,
                 request.registry.fallback_url)
        package, data = fetch_dist(request, dist)
        disp = CONTENT_DISPOSITION.tuples(filename=package.filename)
        request.response.headers.update(disp)
        request.response.body = data
        request.response.content_type = 'application/octet-stream'
        return request.response
    response = request.db.download_response(package)
    return response


@view_config(context=APIPackageFileResource, request_method='POST',
             subpath=(), renderer='json', permission='write')
@argify
def upload_package(context, request, content):
    """ Upload a package """
    try:
        return request.db.upload(content.filename, content.file,
                                 name=context.name)
    except ValueError as e:  # pragma: no cover
        return HTTPBadRequest(*e.args)


@view_config(context=APIPackageFileResource, request_method='DELETE',
             subpath=(), permission='write')
def delete_package(context, request):
    """ Delete a package """
    package = request.db.fetch(context.filename)
    if package is None:
        return HTTPBadRequest("Could not find %s" % context.filename)
    request.db.delete(package)
    return request.response


@view_config(context=APIResource, name='user', request_method='PUT',
             subpath=('username/*'), renderer='json',
             permission=NO_PERMISSION_REQUIRED)
@argify
def register(request, password):
    """ Register a user """
    if not request.access.allow_register and not request.access.need_admin():
        return HTTPNotFound()
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


@view_config(context=APIResource, name='fetch', renderer='json',
             permission=NO_PERMISSION_REQUIRED)
@argify(wheel=bool, prerelease=bool)
def fetch_requirements(request, requirements, wheel=True, prerelease=False):
    """
    Fetch packages from the fallback_url

    Parameters
    ----------
    requirements : str
        Requirements in the requirements.txt format (with newlines)
    wheel : bool, optional
        If True, will prefer wheels (default True)
    prerelease : bool, optional
        If True, will allow prerelease versions (default False)

    Returns
    -------
    pkgs : list
        List of Package objects

    """
    if not request.access.can_update_cache():
        return HTTPForbidden()
    locator = BetterScrapingLocator(request.registry.fallback_url, wheel=wheel)
    packages = []
    for line in requirements.splitlines():
        dist = locator.locate(line, prerelease)
        if dist is not None:
            try:
                packages.append(fetch_dist(request, dist)[0])
            except ValueError:
                pass
    return {
        'pkgs': packages,
    }
