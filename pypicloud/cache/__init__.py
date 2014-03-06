""" Caching database implementations """
from pyramid.path import DottedNameResolver

from .base import ICache
from .redis_cache import RedisCache
from .sql import SQLCache


def get_cache_impl(settings):
    """ Get and configure the cache db wrapper """
    resolver = DottedNameResolver(__name__)
    dotted_cache = settings.get('pypi.db', 'sql')
    if dotted_cache == 'sql':
        dotted_cache = 'pypicloud.cache.SQLCache'
    elif dotted_cache == 'redis':
        dotted_cache = 'pypicloud.cache.RedisCache'
    elif dotted_cache == 'dynamo':
        dotted_cache = 'pypicloud.cache.dynamo.DynamoCache'
    cache_impl = resolver.resolve(dotted_cache)
    cache_impl.configure(settings)
    cache_impl.reload_if_needed()
    return cache_impl
