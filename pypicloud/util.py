""" Utilities """
from distlib.util import split_filename
from distlib.locators import Locator

ALL_EXTENSIONS = Locator.source_extensions + Locator.binary_extensions


def parse_filename(filename, name=None):
    """ Parse a name and version out of a filename """
    version = None
    for ext in ALL_EXTENSIONS:
        if filename.endswith(ext):
            trimmed = filename[:-len(ext)]
            parsed_name, version = split_filename(trimmed, name)[:2]
            break
    if version is None:
        raise ValueError("Cannot parse package file '%s'" % filename)
    if name is None:
        name = parsed_name
    return normalize_name(name), version


def normalize_name(name):
    """ Normalize a python package name """
    return name.lower().replace('-', '_')
