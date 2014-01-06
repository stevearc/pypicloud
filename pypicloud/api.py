""" Common api functions extracted from the view logic """
from boto.s3.key import Key
from hashlib import md5
from pypicloud.models import Package
from pyramid.httpexceptions import HTTPNotFound, HTTPBadRequest


def list_packages(request):
    """ Get the names of all unique packages, filtered by read permission """
    names = Package.distinct(request)
    if (not request.registry.zero_security_mode and
            not request.is_admin(request.userid)):
        i = 0
        while i < len(names):
            name = names[i]
            if not request.has_permission(name, 'r'):
                del names[i]
                continue
            i += 1

    return names


def upload_package(request, name, version, content):
    """
    Upload a package to S3 and save to our caching database

    Parameters
    ----------
    request : :class:`~pyramid.request.Request`
    name : str
        The name of the package (will be normalized)
    version : str
        The version string ot the package
    content : :class:`~cgi.FieldStorage`
        The file upload field generated from a multipart/form-data POST

    """
    name = Package.normalize_name(name)
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
    pkg = Package.fetch(request, name, version)
    if pkg is None:
        pkg = Package(name, version, key.key)
        pkg.save(request)
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
    return pkg


def delete_package(request, name, version):
    """
    Delete a package

    Parameters
    ----------
    request : :class:`~pyramid.request.Request`
    name : str
        The name of the package
    version : str
        The version of the package to delete

    """
    name = Package.normalize_name(name)
    package = Package.fetch(request, name, version)
    if package is None:
        raise HTTPNotFound("Could not find %s==%s" % (name, version))
    key = Key(request.bucket)
    key.key = package.path
    key.delete()
    package.delete(request)
