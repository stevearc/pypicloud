""" Classes that provide user and package permissions """
from functools import partial
from pyramid.path import DottedNameResolver

from .config import ConfigAccessBackend
from .base import IAccessBackend, IMutableAccessBackend, pwd_context
from .remote import RemoteAccessBackend
from .sql import SQLAccessBackend
from pypicloud.util import getdefaults


def includeme(config):
    """ Configure the app """
    settings = config.get_settings()

    resolver = DottedNameResolver(__name__)
    dotted_name = getdefaults(settings, 'pypi.auth', 'pypi.access_backend',
                              'config')
    if dotted_name == 'config':
        dotted_name = ConfigAccessBackend
    elif dotted_name == 'remote':
        dotted_name = RemoteAccessBackend
    elif dotted_name == 'sql':
        dotted_name = SQLAccessBackend
    elif dotted_name == 'ldap':
        dotted_name = "pypicloud.access.ldap_.LDAPAccessBackend"
    access_backend = resolver.maybe_resolve(dotted_name)
    kwargs = access_backend.configure(settings)
    config.add_request_method(partial(access_backend, **kwargs), name='access',
                              reify=True)
