""" Views """
from boto.s3.key import Key
from pyramid.httpexceptions import HTTPBadRequest, HTTPFound, HTTPNotFound
from pyramid.view import view_config

from .models import Package


@view_config(route_name='index', request_method='GET', renderer='index.jinja2')
def get_index(request):
    """ Render a home screen """
    from .__version__ import __version__
    return {'version': __version__}


@view_config(route_name='index', request_method='POST', permission='update')
def update(request):
    """ Handle update commands """
    action = request.param(':action')
    if action == 'verify':
        return request.response
    elif action == 'submit':
        return request.response
    elif action == 'doc_upload':
        return request.response
    elif action == 'remove_pkg':
        name = request.param("name")
        version = request.param("version")
        package = Package(name, version)
        try:
            index = request.packages.index(package)
            package = request.packages[index]
        except ValueError:
            raise HTTPNotFound("Could not find %s==%s" % (name, version))
        key = Key(request.bucket)
        key.key = request.registry.path + package.filename
        key.delete()
        return request.response
    elif action == 'file_upload':
        filename = request.POST['content'].filename
        data = request.POST['content'].file
        if '/' in filename:
            raise HTTPBadRequest("Invalid file path '%s'" % filename)
        key = Key(request.bucket)
        key.key = request.registry.path + filename
        key.set_contents_from_file(data)
        return request.response
    else:
        raise HTTPBadRequest("Unknown action '%s'" % action)


@view_config(route_name='simple', request_method='GET',
             renderer='simple.jinja2')
def simple(request):
    """ Render the list of all unique package names """
    unique_pkgs = set((pkg.name for pkg in request.packages))
    return {'pkgs': sorted(unique_pkgs)}


@view_config(route_name='packages', request_method='GET',
             renderer='package.jinja2')
def all_packages(request):
    """ Render all package file names """
    return {'pkgs': request.packages}


@view_config(route_name='package_versions', request_method='GET',
             renderer='package.jinja2')
def package_versions(request):
    """ Render the links for all versions of a package """
    package_name = request.matchdict['package']
    package = Package(package_name)

    pkgs = [pkg for pkg in request.packages if pkg.name == package.name]
    if request.registry.use_fallback and not pkgs:
        redirect_url = "%s/%s/" % (
            request.registry.fallback_url.rstrip('/'), package)
        return HTTPFound(location=redirect_url)
    return {'pkgs': pkgs}
