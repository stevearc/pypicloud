""" Views for simple pip interaction """
import logging
import posixpath

import pkg_resources
from pyramid.httpexceptions import HTTPBadRequest, HTTPConflict, HTTPFound, HTTPNotFound
from pyramid.view import view_config
from pyramid_duh import addslash, argify
from pyramid_rpc.xmlrpc import xmlrpc_method

from pypicloud.route import Root, SimplePackageResource, SimpleResource
from pypicloud.util import normalize_name, parse_filename

LOG = logging.getLogger(__name__)


@view_config(context=Root, request_method="POST", subpath=(), renderer="json")
@view_config(context=SimpleResource, request_method="POST", subpath=(), renderer="json")
@argify
def upload(
    request, content, name=None, version=None, summary=None, requires_python=None
):
    """ Handle update commands """
    action = request.param(":action", "file_upload")
    # Direct uploads from the web UI go here, and don't have a name/version
    if name is None or version is None:
        name, version = parse_filename(content.filename)
    else:
        name = normalize_name(name)
    if action == "file_upload":
        if not request.access.has_permission(name, "write"):
            return request.forbid()
        try:
            return request.db.upload(
                content.filename,
                content.file,
                name=name,
                version=version,
                summary=summary,
                requires_python=requires_python or None,
            )
        except ValueError as e:
            return HTTPConflict(*e.args)
    else:
        return HTTPBadRequest("Unknown action '%s'" % action)


@xmlrpc_method(endpoint="pypi")
@xmlrpc_method(endpoint="pypi_slash")
def search(request, criteria, query_type):
    """
    Perform searches from pip. This handles XML RPC requests to the "pypi"
    endpoint (configured as /pypi/) that specify the method "search".

    """
    filtered = []
    for pkg in request.db.search(criteria, query_type):
        if request.access.has_permission(pkg.name, "read"):
            filtered.append(pkg.search_summary())
    return filtered


@view_config(
    context=SimpleResource, request_method="GET", subpath=(), renderer="simple.jinja2"
)
@addslash
def simple(request):
    """ Render the list of all unique package names """
    names = request.db.distinct()
    i = 0
    while i < len(names):
        name = names[i]
        if not request.access.has_permission(name, "read"):
            del names[i]
            continue
        i += 1
    return {"pkgs": names}


def _package_versions(context, request):
    """ Render the links for all versions of a package """
    fallback = request.registry.fallback
    if fallback == "redirect":
        if request.registry.always_show_upstream:
            return _simple_redirect_always_show(context, request)
        else:
            return _simple_redirect(context, request)
    elif fallback == "cache":
        if request.registry.always_show_upstream:
            return _simple_cache_always_show(context, request)
        else:
            return _simple_cache(context, request)
    else:
        return _simple_serve(context, request)


@view_config(
    context=SimplePackageResource,
    request_method="GET",
    subpath=(),
    renderer="package.jinja2",
)
@addslash
def package_versions(context, request):
    """ Render the links for all versions of a package """
    return _package_versions(context, request)


@view_config(
    context=SimplePackageResource,
    name="json",
    request_method="GET",
    subpath=(),
    renderer="json",
)
def package_versions_json(context, request):
    """ Render the package versions in JSON format """
    pkgs = _package_versions(context, request)
    if not isinstance(pkgs, dict):
        return pkgs
    response = {"info": {"name": context.name}, "releases": {}}
    max_version = None
    for filename, pkg in pkgs["pkgs"].items():
        name, version_str = parse_filename(filename)
        version = pkg_resources.parse_version(version_str)
        if max_version is None or version > max_version:
            max_version = version

        release = {
            "filename": filename,
            "url": pkg.get("non_hashed_url", pkg["url"]),
            "requires_python": pkg["requires_python"],
        }
        if pkg.get("hash_sha256"):
            release["digests"] = {"md5": pkg["hash_md5"], "sha256": pkg["hash_sha256"]}
            release["md5_digest"] = pkg["hash_md5"]

        response["releases"].setdefault(version_str, []).append(release)
    if max_version is not None:
        response["urls"] = response["releases"].get(str(max_version), [])
    return response


def get_fallback_packages(request, package_name, redirect=True):
    """ Get all package versions for a package from the fallback_base_url """
    releases = request.locator.get_releases(package_name)
    pkgs = {}
    if not request.access.has_permission(package_name, "fallback"):
        return pkgs
    for release in releases:
        url = release["url"]
        filename = posixpath.basename(url)
        if not redirect:
            url = request.app_url("api", "package", release["name"], filename)
        pkgs[filename] = {
            "url": url,
            "requires_python": release["requires_python"],
            "hash_sha256": release["digests"].get("sha256"),
            "hash_md5": release["digests"].get("md5"),
        }
    return pkgs


def packages_to_dict(request, packages):
    """ Convert a list of packages to a dict used by the template """
    pkgs = {}
    for package in packages:
        url = package.get_url(request)
        # We could also do with a url without the sha256 fragment for the JSON api
        non_fragment_url = url
        if "#sha256=" in url:
            non_fragment_url = non_fragment_url[: url.find("#sha256=")]

        pkgs[package.filename] = {
            "url": url,
            "non_hashed_url": non_fragment_url,
            "requires_python": package.data.get("requires_python"),
            "hash_sha256": package.data.get("hash_sha256"),
            "hash_md5": package.data.get("hash_md5"),
        }
    return pkgs


def _pkg_response(pkgs):
    """ Take a package mapping and return either a dict for jinja or a 404 """
    if pkgs:
        return {"pkgs": pkgs}
    else:
        return HTTPNotFound("No packages found")


def _redirect(context, request):
    """ Return a 302 to the fallback url for this package """
    if request.registry.fallback_base_url:
        path = request.path.lstrip("/")
        redirect_url = "%s/%s" % (request.registry.fallback_base_url.rstrip("/"), path)
    else:
        redirect_url = "%s/%s/" % (
            request.registry.fallback_url.rstrip("/"),
            context.name,
        )

    return HTTPFound(location=redirect_url)


def _simple_redirect(context, request):
    """ Service /simple with fallback=redirect """
    normalized_name = normalize_name(context.name)
    packages = request.db.all(normalized_name)
    if packages:
        if not request.access.has_permission(normalized_name, "read"):
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
        if not request.access.has_permission(normalized_name, "read"):
            if request.is_logged_in:
                return _redirect(context, request)
            else:
                return request.request_login()
        else:
            pkgs = get_fallback_packages(request, context.name)
            stored_pkgs = packages_to_dict(request, packages)
            # Overwrite existing package urls
            for filename, url in stored_pkgs.items():
                pkgs[filename] = url
            return _pkg_response(pkgs)
    else:
        return _redirect(context, request)


def _simple_cache(context, request):
    """ Service /simple with fallback=cache """
    normalized_name = normalize_name(context.name)

    if not request.access.has_permission(normalized_name, "read"):
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

    if not request.access.has_permission(normalized_name, "read"):
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
                for filename, data in stored_pkgs.items():
                    pkgs[filename] = data
                return _pkg_response(pkgs)
            else:
                return request.request_login()
        else:
            pkgs = get_fallback_packages(request, context.name, False)
            stored_pkgs = packages_to_dict(request, packages)
            # Overwrite existing package urls
            for filename, data in stored_pkgs.items():
                pkgs[filename] = data
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

    if not request.access.has_permission(normalized_name, "read"):
        if request.is_logged_in:
            return HTTPNotFound("No packages found named %r" % normalized_name)
        else:
            return request.request_login()

    packages = request.db.all(normalized_name)
    return _pkg_response(packages_to_dict(request, packages))
