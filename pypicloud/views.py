""" Views """
from pip.util import normalize_name
from sqlalchemy import distinct
from boto.s3.key import Key
from pyramid.httpexceptions import HTTPBadRequest, HTTPFound, HTTPNotFound
from pyramid.view import view_config

from . import __version__
from .models import Package


@view_config(route_name='index', request_method='GET', renderer='index.jinja2')
def get_index(request):
    """ Render a home screen """
    return {'version': __version__}


@view_config(route_name='index', request_method='POST', permission='update')
def update(request):
    """ Handle update commands """
    action = request.param(':action')
    if action == 'remove_pkg':
        name = normalize_name(request.param("name"))
        version = request.param("version")
        request.fetch_packages_if_needed()
        package = request.db.query(Package).filter_by(name=name,
                                                      version=version).first()
        if package is None:
            raise HTTPNotFound("Could not find %s==%s" % (name, version))
        key = Key(request.bucket)
        key.key = package.path
        key.delete()
        request.db.delete(package)
        return request.response
    elif action == 'file_upload':
        request.fetch_packages_if_needed()
        name = normalize_name(request.param('name'))
        version = request.param('version')
        content = request.param('content')
        filename = content.filename
        data = content.file
        if '/' in filename:
            raise HTTPBadRequest("Invalid file path '%s'" % filename)
        key = Key(request.bucket)
        key.key = request.registry.prefix + filename
        key.set_metadata('name', name)
        key.set_metadata('version', version)
        key.set_contents_from_file(data)
        pkg = request.db.query(Package).filter_by(name=name,
                                                  version=version).first()
        if pkg is None:
            pkg = Package(name, version, key.key)
            request.db.add(pkg)
        elif pkg.path != key.key:
            # If we're overwriting the same package with a different filename,
            # make sure we delete the old file in S3
            old_key = Key(request.bucket)
            old_key.key = pkg.path
            old_key.delete()
            pkg.path = key.key
        return request.response
    else:
        raise HTTPBadRequest("Unknown action '%s'" % action)


@view_config(route_name='simple', request_method='GET',
             renderer='simple.jinja2')
def simple(request):
    """ Render the list of all unique package names """
    request.fetch_packages_if_needed()
    names = request.db.query(distinct(Package.name))\
        .order_by(Package.name).all()
    return {'pkgs': [n[0] for n in names]}


@view_config(route_name='packages', request_method='GET',
             renderer='package.jinja2')
def all_packages(request):
    """ Render all package file names """
    request.fetch_packages_if_needed()
    packages = request.db.query(Package).order_by(Package.name,
                                                  Package.version).all()
    return {'pkgs': packages}


@view_config(route_name='package_versions', request_method='GET',
             renderer='package.jinja2')
def package_versions(request):
    """ Render the links for all versions of a package """
    name = normalize_name(request.matchdict['package'])

    request.fetch_packages_if_needed()
    pkgs = request.db.query(Package).filter_by(name=name)\
        .order_by(Package.version).all()
    if request.registry.use_fallback and not pkgs:
        redirect_url = "%s/%s/" % (
            request.registry.fallback_url.rstrip('/'), name)
        return HTTPFound(location=redirect_url)
    return {'pkgs': pkgs}
