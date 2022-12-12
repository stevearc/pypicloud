""" Utilities """
import logging
import os
import re
import time
import unicodedata
from typing import (
    IO,
    Any,
    AnyStr,
    Callable,
    Dict,
    ItemsView,
    Iterator,
    KeysView,
    List,
    Optional,
    Tuple,
    Union,
)

from distlib.locators import Locator
from distlib.util import split_filename
from distlib.wheel import Wheel

LOG = logging.getLogger(__name__)
ALL_EXTENSIONS = Locator.source_extensions + Locator.binary_extensions
SENTINEL = object()
CHUNK_SIZE = 1 << 20  # read 1MB chunks


class PackageParseError(ValueError):
    pass


def parse_filename(filename: str, name: Optional[str] = None) -> Tuple[str, str]:
    """Parse a name and version out of a filename"""
    version = None
    for ext in ALL_EXTENSIONS:
        if filename.endswith(ext):
            if ext == ".whl":
                wheel = Wheel(filename)
                return wheel.name, wheel.version
            trimmed = filename[: -len(ext)]
            parsed = split_filename(trimmed, name)
            if parsed is None:
                break
            else:
                parsed_name, version = parsed[:2]
            break
    if version is None:
        raise PackageParseError("Cannot parse package file '%s'" % filename)
    if name is None:
        name = parsed_name
    return normalize_name(name), version


def get_packagetype(name: str) -> str:
    """Get package type out of a filename"""
    if name.endswith(".tar.gz"):
        return "sdist"
    elif name.endswith(".egg"):
        return "bdist_egg"
    elif name.endswith(".whl"):
        return "bdist_wheel"
    else:
        return ""


def normalize_name(name: str) -> str:
    """Normalize a python package name"""
    # Lifted directly from PEP503:
    # https://www.python.org/dev/peps/pep-0503/#id4
    return re.sub(r"[-_.]+", "-", name).lower()


def normalize_metadata_value(value: Union[str, bytes]) -> str:
    """Strip non-ASCII characters from metadata values"""
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        value = "".join(c for c in unicodedata.normalize("NFKD", value) if ord(c) < 128)
    return re.sub(r"\s+", " ", value)


def normalize_metadata(metadata: Dict[str, Union[str, bytes]]) -> Dict[str, str]:
    """
    Strip non-ASCII characters from metadata values
    and replace "_" in metadata keys to "-"
    """
    return {
        key.replace("_", "-"): normalize_metadata_value(value)
        for key, value in metadata.items()
    }


def create_matcher(queries: List[str], query_type: str) -> Callable[[str], bool]:
    """
    Create a matcher for a list of queries

    Parameters
    ----------
    queries : list
        List of queries

    query_type: str
        Type of query to run: ["or"|"and"]

    Returns
    -------
        Matcher function

    """
    queries = [query.lower() for query in queries]
    if query_type == "or":
        return lambda x: any((q in x.lower() for q in queries))
    else:
        return lambda x: all((q in x.lower() for q in queries))


def stream_file(fp: IO[AnyStr], chunk_size: int = CHUNK_SIZE) -> Iterator[AnyStr]:
    """
    Read an (opened) file in chunks of chunk_size bytes
    """
    while True:
        chunk = fp.read(chunk_size)
        if not chunk:
            break
        yield chunk


class EnvironSettings:
    def __init__(self, settings: Dict[str, Any], env: Optional[Dict[str, str]] = None):
        self._settings = settings
        if env is None:
            self._env = dict(os.environ)
        else:
            self._env = env

    @staticmethod
    def _get_environ_key(key: str) -> str:
        return "PPC_" + key.upper().replace(".", "_")

    def __iter__(self) -> Iterator[str]:
        return iter(self._settings)

    def keys(self) -> KeysView[str]:
        return self._settings.keys()

    def items(self) -> ItemsView[str, Any]:
        return self._settings.items()

    def __contains__(self, key: str) -> bool:
        env_key = self._get_environ_key(key)
        return env_key in self._env or key in self._settings

    def __setitem__(self, key: str, value: str) -> None:
        env_key = self._get_environ_key(key)
        self._env.pop(env_key, None)
        self._settings[key] = value

    def __getitem__(self, key: str) -> str:
        env_key = self._get_environ_key(key)
        if env_key in self._env:
            return self._env[env_key]
        return self._settings[key]

    def __str__(self) -> str:
        return str(self._settings)

    def __repr__(self) -> str:
        return "EnvironSettings(%s)" % self._settings

    def read_prefix_from_environ(self, prefix: str) -> None:
        if not prefix:
            return
        # Make sure the prefix has a '.' at the end (e.g. "sqlalchemy.")
        if prefix[-1] == "_":
            prefix = prefix[:-1] + "."
        elif prefix[-1] != ".":
            prefix = prefix + "."
        env_prefix = self._get_environ_key(prefix)
        for key, val in self._env.items():
            if key.startswith(env_prefix):
                setting_key = prefix + key[len(env_prefix) :].lower()
                self._settings[setting_key] = val

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key: str, default: Any = SENTINEL) -> Any:
        env_key = self._get_environ_key(key)
        if env_key in self._env:
            self._settings.pop(key, None)
            return self._env.pop(env_key)
        try:
            return self._settings.pop(key)
        except KeyError:
            if default is SENTINEL:
                raise
            else:
                return default

    def setdefault(self, key: str, value: Any) -> Any:
        try:
            return self[key]
        except KeyError:
            self._settings[key] = value
            return value

    def get_as_dict(
        self, prefix: str, **kwargs: Callable[[Any], Any]
    ) -> Dict[str, Any]:
        """
        Convenience method for fetching settings

        Returns a dict; any settings that were missing from the config file will
        not be present in the returned dict (as opposed to being present with a
        None value)

        Parameters
        ----------
        prefix : str
            String to prefix all keys with when fetching value from settings
        **kwargs : dict
            Mapping of setting name to conversion function (e.g. str or asbool)

        """
        computed = {}
        for name, fxn in kwargs.items():
            val = self.get(prefix + name)
            if val is not None:
                computed[name] = fxn(val)
        return computed

    def clone(self) -> "EnvironSettings":
        return EnvironSettings(dict(self._settings), dict(self._env))


class TimedCache(dict):
    """
    Dict that will store entries for a given time, then evict them

    Parameters
    ----------
    cache_time : int or None
        The amount of time to cache entries for, in seconds. 0 will not cache.
        None will cache forever.
    factory : callable, optional
        If provided, when the TimedCache is accessed and has no value, it will
        attempt to populate itself by calling this function with the key it was
        accessed with. This function should return a value to cache, or None if
        no value is found.

    """

    def __init__(
        self, cache_time: Optional[int], factory: Optional[Callable[[Any], Any]] = None
    ):
        super(TimedCache, self).__init__()
        if cache_time is not None and cache_time < 0:
            raise ValueError("cache_time cannot be negative")
        self._cache_time = cache_time
        self._factory = factory
        self._times = {}  # type: Dict[str, float]

    def _has_expired(self, key):
        """Check if a key is both present and expired"""
        if key not in self._times or self._cache_time is None:
            return False
        updated = self._times[key]
        return updated is not None and time.time() - updated > self._cache_time

    def _evict(self, key):
        """Remove a key if it has expired"""
        if self._has_expired(key):
            del self[key]

    def __contains__(self, key):
        self._evict(key)
        return super(TimedCache, self).__contains__(key)

    def __delitem__(self, key):
        del self._times[key]
        super(TimedCache, self).__delitem__(key)

    def __setitem__(self, key, value):
        if self._cache_time == 0:
            return
        self._times[key] = time.time()
        super(TimedCache, self).__setitem__(key, value)

    def __getitem__(self, key):
        self._evict(key)
        try:
            value = super(TimedCache, self).__getitem__(key)
        except KeyError:
            if self._factory:
                value = self._factory(key)
                if value is None:
                    raise
                self[key] = value
            else:
                raise
        return value

    def get(self, key, default=None):
        self._evict(key)
        value = super(TimedCache, self).get(key, SENTINEL)
        if value is SENTINEL:
            if self._factory is not None:
                value = self._factory(key)
                if value is not None:
                    self[key] = value
                    return value
                else:
                    return default
            else:
                return default
        else:
            return value

    def set_expire(self, key, value, expiration):
        """
        Set a value in the cache with a specific expiration

        Parameters
        ----------
        key : str
        value : value
        expiration : int or None
            Sets the value to expire this many seconds from now. If None, will
            never expire.

        """
        if expiration is not None:
            if expiration <= 0:
                try:
                    del self[key]
                except KeyError:
                    pass
                return
            expiration = time.time() + expiration - self._cache_time

        self._times[key] = expiration
        super(TimedCache, self).__setitem__(key, value)
