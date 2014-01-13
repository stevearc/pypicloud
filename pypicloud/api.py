""" Common api functions extracted from the view logic """
from pyramid.httpexceptions import HTTPBadRequest


def list_packages(request):
    """ Get the names of all unique packages, filtered by read permission """
    names = request.db.distinct()
    i = 0
    while i < len(names):
        name = names[i]
        if not request.access.has_permission(name, 'read'):
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
    try:
        return request.db.upload(name, version, content.filename, content.file)
    except ValueError as e:
        raise HTTPBadRequest(*e.args)
