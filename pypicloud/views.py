""" Views """
from boto.s3.key import Key
from hashlib import md5
from pyramid.httpexceptions import HTTPBadRequest, HTTPFound, HTTPNotFound
from pyramid.view import view_config
from sqlalchemy import distinct

from . import __version__
from .models import Package
from .route import Root, subpath, addslash


@view_config(route_name='root', request_method='GET', renderer='index.jinja2')
@view_config(context=Root, name='pypi', request_method='GET',
             renderer='index.jinja2')
def get_index(request):
    """ Render a home screen """
    return {'version': __version__}


@view_config(route_name='root', request_method='POST', permission='update')
def update(request):
    """ Handle update commands """
    action = request.param(':action')
    if action == 'remove_pkg':
        name = Package.normalize_name(request.param("name"))
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
        name = Package.normalize_name(request.param('name'))
        version = request.param('version')
        content = request.param('content')
        filename = content.filename
        data = content.file
        if '/' in filename:
            raise HTTPBadRequest("Invalid file path '%s'" % filename)
        key = Key(request.bucket)
        if request.registry.prepend_hash:
            m = md5()
            m.update(name)
            m.update(version)
            prefix = m.digest().encode('hex')[:4]
            filename = prefix + '-' + filename
        key.key = request.registry.prefix + filename
        key.set_metadata('name', name)
        key.set_metadata('version', version)
        pkg = request.db.query(Package).filter_by(name=name,
                                                  version=version).first()
        if pkg is None:
            pkg = Package(name, version, key.key)
            request.db.add(pkg)
        elif not request.registry.allow_overwrite:
            raise HTTPBadRequest("Package '%s==%s' already exists!" %
                                 (name, version))
        elif pkg.path != key.key:
            # If we're overwriting the same package with a different filename,
            # make sure we delete the old file in S3
            old_key = Key(request.bucket)
            old_key.key = pkg.path
            old_key.delete()
            pkg.path = key.key

        key.set_contents_from_file(data)
        return request.response
    else:
        raise HTTPBadRequest("Unknown action '%s'" % action)


@view_config(context=Root, name='simple', request_method='GET',
             renderer='simple.jinja2')
@addslash
def simple(request):
    """ Render the list of all unique package names """
    request.fetch_packages_if_needed()
    names = request.db.query(distinct(Package.name))\
        .order_by(Package.name).all()
    return {'pkgs': [n[0] for n in names]}


@view_config(context=Root, name='packages', request_method='GET',
             renderer='package.jinja2')
@addslash
def all_packages(request):
    """ Render all package file names """
    request.fetch_packages_if_needed()
    packages = request.db.query(Package).order_by(Package.name,
                                                  Package.version).all()
    return {'pkgs': packages}


@view_config(context=Root, name='simple', request_method='GET',
             renderer='package.jinja2', custom_predicates=(subpath('*'),))
@addslash
def package_versions(request):
    """ Render the links for all versions of a package """
    name = Package.normalize_name(request.subpath[0])

    request.fetch_packages_if_needed()
    pkgs = request.db.query(Package).filter_by(name=name)\
        .order_by(Package.version).all()
    if request.registry.use_fallback and not pkgs:
        redirect_url = "%s/%s/" % (
            request.registry.fallback_url.rstrip('/'), name)
        return HTTPFound(location=redirect_url)
    return {'pkgs': pkgs}
