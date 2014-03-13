""" Caching database implementations """
from functools import partial
from pyramid.path import DottedNameResolver

from .base import ICache
from .redis_cache import RedisCache
from .sql import SQLCache


def includeme(config):
    """ Get and configure the cache db wrapper """
    settings = config.get_settings()
    resolver = DottedNameResolver(__name__)
    dotted_cache = settings.get('pypi.db', 'sql')
    if dotted_cache == 'sql':
        dotted_cache = 'pypicloud.cache.SQLCache'
    elif dotted_cache == 'redis':
        dotted_cache = 'pypicloud.cache.RedisCache'
    elif dotted_cache == 'dynamo':
        dotted_cache = 'pypicloud.cache.dynamo.DynamoCache'
    cache_impl = resolver.resolve(dotted_cache)
    kwargs = cache_impl.configure(settings)
    cache = cache_impl(**kwargs)
    cache.reload_if_needed()
    config.add_request_method(partial(cache_impl, **kwargs), name='db',
                              reify=True)
    return cache_impl
