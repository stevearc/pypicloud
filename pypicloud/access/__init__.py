""" Classes that provide user and package permissions """
from pyramid.path import DottedNameResolver

from .config import ConfigAccessBackend
from .base import IAccessBackend, IMutableAccessBackend, pwd_context
from .remote import RemoteAccessBackend
from .sql import SQLAccessBackend


def includeme(config):
    """ Configure the app """
    settings = config.get_settings()

    resolver = DottedNameResolver(__name__)
    dotted_name = settings.get('pypi.access_backend', 'config')
    if dotted_name == 'config':
        dotted_name = ConfigAccessBackend
    elif dotted_name == 'remote':
        dotted_name = RemoteAccessBackend
    elif dotted_name == 'sql':
        dotted_name = SQLAccessBackend
    access_backend = resolver.maybe_resolve(dotted_name)
    access_backend.configure(settings)
    config.add_request_method(access_backend, name='access', reify=True)
