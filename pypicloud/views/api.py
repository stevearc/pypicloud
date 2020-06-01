""" Views for simple api calls that return json data """
import logging
import posixpath
from contextlib import closing
from io import BytesIO
from urllib.request import urlopen

# pylint: disable=E0611,W0403
from paste.httpheaders import CACHE_CONTROL, CONTENT_DISPOSITION

# pylint: enable=E0611,W0403
from pyramid.httpexceptions import HTTPBadRequest, HTTPForbidden, HTTPNotFound
from pyramid.security import NO_PERMISSION_REQUIRED
from pyramid.view import view_config
from pyramid_duh import addslash, argify

from pypicloud.route import (
    APIPackageFileResource,
    APIPackageResource,
    APIPackagingResource,
    APIResource,
)
from pypicloud.util import normalize_name

from .login import handle_register_request

LOG = logging.getLogger(__name__)


@view_config(
    context=APIPackagingResource, request_method="GET", subpath=(), renderer="json"
)
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
        name = package if isinstance(package, str) else package["name"]
        if not request.access.has_permission(name, "read"):
            del packages[i]
            continue
        i += 1
    return {"packages": packages}


@view_config(
    context=APIPackageResource,
    request_method="GET",
    subpath=(),
    renderer="json",
    permission="read",
)
@addslash
def package_versions(context, request):
    """ List all unique package versions """
    normalized_name = normalize_name(context.name)
    versions = request.db.all(normalized_name)
    return {
        "packages": versions,
        "write": request.access.has_permission(normalized_name, "write"),
    }


def fetch_dist(request, url, name, version, summary, requires_python):
    """ Fetch a Distribution and upload it to the storage backend """
    filename = posixpath.basename(url)
    handle = urlopen(url)
    with closing(handle):
        data = handle.read()
    # TODO: digest validation
    return (
        request.db.upload(
            filename, BytesIO(data), name, version, summary, requires_python
        ),
        data,
    )


@view_config(context=APIPackageFileResource, request_method="GET", permission="read")
def download_package(context, request):
    """ Download package, or redirect to the download link """
    package = request.db.fetch(context.filename)
    if not package:
        if request.registry.fallback != "cache":
            return HTTPNotFound()
        if not request.access.can_update_cache():
            return request.forbid()
        # If we are caching pypi, download the package from pypi and save it
        releases = request.locator.get_releases(context.name)

        dist = None
        for release in releases:
            if posixpath.basename(release["url"]) == context.filename:
                dist = release
                break
        if dist is None:
            return HTTPNotFound()
        LOG.info("Caching %s from %s", context.filename, request.fallback_simple)
        package, data = fetch_dist(
            request,
            dist["url"],
            dist["name"],
            dist["version"],
            dist["summary"],
            dist["requires_python"],
        )
        disp = CONTENT_DISPOSITION.tuples(filename=package.filename)
        request.response.headers.update(disp)
        cache_control = CACHE_CONTROL.tuples(
            public=True, max_age=request.registry.package_max_age
        )
        request.response.headers.update(cache_control)
        request.response.body = data
        request.response.content_type = "application/octet-stream"
        return request.response
    if request.registry.stream_files:
        with request.db.storage.open(package) as data:
            request.response.body = data.read()
        disp = CONTENT_DISPOSITION.tuples(filename=package.filename)
        request.response.headers.update(disp)
        cache = CACHE_CONTROL.tuples(
            public=True, max_age=request.registry.package_max_age
        )
        request.response.headers.update(cache)
        request.response.content_type = "application/octect-stream"
        return request.response
    response = request.db.download_response(package)
    return response


@view_config(
    context=APIPackageFileResource,
    request_method="POST",
    subpath=(),
    renderer="json",
    permission="write",
)
@argify
def upload_package(context, request, content, summary=None, requires_python=None):
    """ Upload a package """
    try:
        return request.db.upload(
            content.filename,
            content.file,
            name=context.name,
            summary=summary,
            requires_python=requires_python,
        )
    except ValueError as e:  # pragma: no cover
        return HTTPBadRequest(*e.args)


@view_config(
    context=APIPackageFileResource,
    request_method="DELETE",
    subpath=(),
    permission="write",
)
def delete_package(context, request):
    """ Delete a package """
    package = request.db.fetch(context.filename)
    if package is None:
        return HTTPBadRequest("Could not find %s" % context.filename)
    request.db.delete(package)
    return request.response


@view_config(
    context=APIResource,
    name="user",
    request_method="PUT",
    subpath=("username/*"),
    renderer="json",
    permission=NO_PERMISSION_REQUIRED,
)
@argify
def register(request, password):
    """ Register a user """
    username = request.named_subpaths["username"]
    return handle_register_request(request, username, password)


@view_config(
    context=APIResource,
    name="user",
    subpath=("password"),
    request_method="POST",
    permission="login",
)
@argify
def change_password(request, old_password, new_password):
    """ Change a user's password """
    if not request.access.verify_user(request.userid, old_password):
        return HTTPForbidden()
    request.access.edit_user_password(request.userid, new_password)
    return request.response
