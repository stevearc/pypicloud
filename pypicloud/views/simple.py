""" Views for simple pip interaction """
from pypicloud.route import Root, SimplePackageResource, SimpleResource
from pyramid.httpexceptions import HTTPBadRequest, HTTPFound, HTTPForbidden
from pyramid.view import view_config

from pyramid_duh import argify, addslash


@view_config(context=Root, request_method='POST', subpath=(),
             permission='login', renderer='json')
@view_config(context=SimpleResource, request_method='POST', subpath=(),
             permission='login', renderer='json')
@argify
def upload(request, name, version, content):
    """ Handle update commands """
    action = request.param(':action')
    name = request.db.normalize_name(name)
    if action == 'file_upload':
        if not request.access.has_permission(name, 'write'):
            raise HTTPForbidden()
        try:
            return request.db.upload(name, version, content.filename,
                                     content.file)
        except ValueError as e:
            return HTTPBadRequest(*e.args)
    else:
        raise HTTPBadRequest("Unknown action '%s'" % action)


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
    normalized_name = request.db.normalize_name(context.name)

    pkgs = request.db.all(normalized_name)
    if request.registry.use_fallback and not pkgs:
        redirect_url = "%s/%s/" % (
            request.registry.fallback_url.rstrip('/'), context.name)
        return HTTPFound(location=redirect_url)
    if not request.access.has_permission(normalized_name, 'read'):
        raise HTTPForbidden()
    return {'pkgs': pkgs}
