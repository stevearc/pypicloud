"""
Helper file to generate package version numbers on the fly

You're probably already using git tags to tag releases of your project. If you
aren't, you really should. Wouldn't it be great if your python package
automatically updated its version number based on the most recent git tag? You
know, so you don't have to do it manually all the time? It's almost like
that's a feature that should be available without stupid hacks.

But it's not. So here's how the stupid hacks work.

When you run ``python setup.py``, if you are running it from inside of a git
repository this script with generate a unique version number and embed it in an
auto-generated file in your package. By default the file is named
'_version.py', and you should add it to your ``.gitignore``. Since this is a
python file and it's in your package, it will get bundled up and distributed
with your package. Then during the installation process, this script will
recognize that it is no longer being run from within a git repository and find
the version number from the file it generated earlier.

To use version_helper, first tag a release commit in your repository::

    git tag 0.1.0

Then add the following to your setup.py file::

    from setuptools import setup
    from version_helper import git_version

    setup(
        name='mypackage',
        ...
        **git_version())

You're done! That's it! To view the auto-generated version number of your
package, run::

    python setup.py -V

If you want to embed the version as __version__ (PEP 396), put the following
lines into your package's __init__.py file::

    try:
        from ._version import *  # pylint: disable=F0401,W0401
    except ImportError:
        __version__ = 'unknown'

"""
import locale
import os
import re

import subprocess


# This version regex was constructed from the regex-ish description here:
# http://www.python.org/dev/peps/pep-0440/#public-version-identifiers
VERSION_SCHEME = re.compile(r'^\d+(\.\d+)+'
                            r'((a|b|c|rc)\d+)?'
                            r'(\.post\d+)?'
                            r'(\.dev\d+)?$')
GIT_DESCRIBE = ('git', 'describe')
GIT_DESCRIBE_ARGS = ('--tags', '--dirty', '--abbrev=40', '--long')


def find_package(path):
    """
    Find the directory that contains the python package in a repository

    Parameters
    ----------
    path : str
        The path to the repository

    Returns
    -------
    package_dir : str
        The name of the directory that contains the python package

    Raises
    ------
    error : :class:`IOError`
        If a single package cannot be found

    """
    dirname = os.path.basename(path)
    if os.path.isdir(os.path.join(path, dirname)):
        return dirname
    candidates = []
    for filename in os.listdir(path):
        init = os.path.join(path, filename, '__init__.py')
        if os.path.exists(init):
            candidates.append(filename)
    if len(candidates) == 1:
        return candidates[0]
    elif len(candidates) == 0:
        raise IOError("No package found in repo '%s'" % path)
    else:
        raise IOError("Multiple possible packages found in repo '%s'! "
                      "Please specify one." % path)


def parse_constants(filename):
    """ Parse python constants from a file """
    if not os.path.exists(filename):
        return {
            'source_label': 'NOTAG',
            'version': 'unknown',
        }
    constants = {}
    with open(filename, 'r') as infile:
        for line in infile:
            components = line.split('=')
            if len(components) <= 1:
                continue
            key = components[0].strip(' _')
            value = '='.join(components[1:]).strip().strip('\'\"')
            if key != 'all':
                constants[key] = value
    return constants


def write_constants(filename, **constants):
    """ Write python constants to a file """
    with open(filename, 'w') as outfile:
        outfile.write('""" This file is auto-generated during the '
                      'package-building process """%s' % os.linesep)
        for key, value in constants.items():
            outfile.write("__%s__ = '%s'%s" % (key, value, os.linesep))
        outfile.write('__all__ = %s%s' % (['__%s__' % key for key in
                                           constants], os.linesep))


def git_describe(describe_args):
    """
    Pull the version information from git

    Parameters
    ----------
    describe_args : list
        Arguments for ``describe_cmd`` to be passed to subprocess

    Returns
    -------
    data : dict
        Dictionary of repo data. The fields are listed below

    tag : str
        The git tag for this version
    description : str
        The output of ``git describe``
    is_dev : bool
        True if is_dirty or if addl_commits > 0
    is_dirty : bool
        True if the git repo is dirty
    addl_commits : int
        The number of additional commits on top of the tag ref
    ref : str
        The ref for the current commit
    dirty_suffix : str
        The string that would denote that the working copy is dirty

    Raises
    ------
    error : :class:`subprocess.CalledProcessError`
        If there is an error running ``git describe``

    """
    encoding = locale.getdefaultlocale()[1] or 'utf-8'
    proc = subprocess.Popen(GIT_DESCRIBE + describe_args,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    output = proc.communicate()[0]
    description = output.decode(encoding).strip()
    if proc.returncode != 0:
        print("Error parsing git revision! Make sure that you have tagged a "
              "commit, and that the tag matches the 'tag_match' argument")
        print("Git output: " + description)
        return {
            'tag': 'unknown',
            'description': 'unknown',
            'is_dirty': False,
            'is_dev': False,
            'addl_commits': 0,
            'ref': 'unknown',
            'dirty_suffix': '-dirty',
        }

    components = description.split('-')
    # trim off the dirty suffix
    dirty_suffix = '-dirty'
    is_dirty = False
    for arg in describe_args:
        if arg.startswith('--dirty='):
            dirty_suffix = arg.split('=')[1]
            break
    if dirty_suffix.startswith('-') and components[-1] == dirty_suffix[1:]:
        components = components[:-1]
        is_dirty = True
    elif components[-1].endswith(dirty_suffix):
        components[-1] = components[-1][:-len(dirty_suffix)]
        is_dirty = True

    ref = components[-1][1:]
    addl_commits = int(components[-2])
    tag = '-'.join(components[:-2])
    return {
        'tag': tag,
        'description': description,
        'is_dirty': is_dirty,
        'is_dev': is_dirty or addl_commits > 0,
        'addl_commits': addl_commits,
        'ref': ref,
        'dirty_suffix': dirty_suffix,
    }


def git_version(package=None,
                tag_match='[0-9]*',
                version_mod='_version.py',
                post_process=None,
                source_url_format=None,
                source_url_on_dev=False,
                pep440=False):
    """
    Generate the version from the git revision, or retrieve it from the
    auto-generated module

    Parameters
    ----------
    package : str, optional
        The name of the directory that contains the package's code. If not
        specified, it will be inferred.
    tag_match : str, optional
        Match only tags with this format (default '[0-9]*'). Note that this
        uses glob matching, not PCRE.
    version_mod : str, optional
        The name of the file to write the version into (default '_version.py')
    post_process : callable, optional
        A function that accepts the output of :meth:`.git_describe` and
        optionally mutates it. This can be used to convert custom tags into
        version numbers (ex. 'v0.1' => '0.1') (default None)
    source_url_format : str, optional
        A format string for the url. (ex.
        'https://github.com/pypa/pip/archive/%(version)s.zip') (default None)
    source_url_on_dev : bool, optional
        Attach a source_url even on developer builds (default False)
    pep440 : bool, optional
        If true, create a PEP 440 compatible version number (default False)

    Returns
    -------
    data : dict
        Dictionary of version data. The fields are listed below.

    version : str
        The unique version of this package
    source_label : str
        VERSION-DISTANCE-gHASH
    source_url : str, optional
        A string containing a full URL where the source for this specific
        version of the distribution can be downloaded

    """
    here = os.path.abspath(os.path.dirname(__file__))

    if package is None:
        package = find_package(here)

    version_file_path = os.path.join(here, package, version_mod)

    if not os.path.isdir(os.path.join(here, '.git')):
        return parse_constants(version_file_path)

    describe_args = GIT_DESCRIBE_ARGS
    if tag_match is not None:
        describe_args += ('--match=%s' % tag_match,)
    version_data = git_describe(describe_args)
    if post_process is not None:
        post_process(version_data)
    if version_data['is_dev']:
        if pep440:
            version = (version_data['tag'] +
                       ".post0.dev%(addl_commits)d" % version_data)
        else:
            version = "{tag}-{addl_commits}-g{ref:<.7}".format(**version_data)
            if version_data['is_dirty']:
                version += version_data['dirty_suffix']
    else:
        version = version_data['tag']

    data = {
        'source_label': version_data['description'],
        'version': version,
    }

    if source_url_format is not None and \
            (source_url_on_dev or not version_data['is_dev']):
        data['source_url'] = source_url_format % data
    write_constants(version_file_path, **data)

    if pep440 and not VERSION_SCHEME.match(data['version']):
        raise Exception("Package version '%(version)s' "
                        "is not a valid PEP 440 version string!" % data)

    return data
