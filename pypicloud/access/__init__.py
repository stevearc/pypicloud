""" Classes that provide user and package permissions """
from functools import partial
from pyramid.path import DottedNameResolver

from .aws_secrets_manager import AWSSecretsManagerAccessBackend
from .config import ConfigAccessBackend
from .base import IAccessBackend, IMutableAccessBackend, get_pwd_context, DEFAULT_ROUNDS
from .remote import RemoteAccessBackend
from .sql import SQLAccessBackend


def includeme(config):
    """ Configure the app """
    settings = config.get_settings()

    resolver = DottedNameResolver(__name__)
    dotted_name = settings.get("pypi.auth", "config")
    if dotted_name == "config":
        dotted_name = ConfigAccessBackend
    elif dotted_name == "remote":
        dotted_name = RemoteAccessBackend
    elif dotted_name == "sql":
        dotted_name = SQLAccessBackend
    elif dotted_name == "ldap":
        dotted_name = "pypicloud.access.ldap_.LDAPAccessBackend"
    elif dotted_name == "aws_secrets_manager":
        dotted_name = AWSSecretsManagerAccessBackend
    access_backend = resolver.maybe_resolve(dotted_name)
    kwargs = access_backend.configure(settings)
    config.add_request_method(
        partial(access_backend, **kwargs), name="access", reify=True
    )
    config.add_postfork_hook(partial(access_backend.postfork, **kwargs))
