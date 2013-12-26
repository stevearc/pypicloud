#!/usr/bin/env python
"""
Run selected checks on the current git index

This pre-commit hook was originally based on a hook by Lorenzo Bolla
https://github.com/lbolla/dotfiles/blob/master/githooks/pre-commit

This file was carefully constructed to have no dependencies on other files in
the ``devbox`` package. This allows it to be embedded directly in a project
instead of requiring devbox to be installed.

"""
import fnmatch
import locale
import os
import sys

import contextlib
import json
import shlex
import shutil
import subprocess
import tempfile


CONF_FILE = '.devbox.conf'


@contextlib.contextmanager
def pushd(directory):
    """ CD into the directory inside a 'with' block """
    prevdir = os.getcwd()
    os.chdir(directory)
    try:
        yield prevdir
    finally:
        os.chdir(prevdir)


def check_output(cmd):
    """
    Nice wrapper around subprocess.check_output

    Returns unicode

    """
    encoding = locale.getdefaultlocale()[1] or 'utf-8'
    if hasattr(subprocess, 'check_output'):
        output = subprocess.check_output(cmd)
    else:
        # Python 2.6 doesn't have check_output
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        output = proc.communicate()[0]
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd,
                                                output)
    return output.decode(encoding)


def run_checks(hooks_all, hooks_modified, modified, path):
    """ Run selected checks on the current git index """
    retcode = 0
    for command in hooks_all:
        if not isinstance(command, list):
            command = shlex.split(command)
        retcode |= subprocess.call(command, env={'PATH': path})

    for pattern, command in hooks_modified:
        if not isinstance(command, list):
            command = shlex.split(command)
        for filename in modified:
            if not fnmatch.fnmatch(filename, pattern):
                continue
            printed_filename = False
            proc = subprocess.Popen(command + [filename],
                                    env={'PATH': path},
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
            output = proc.communicate()[0]
            if proc.returncode != 0:
                if not printed_filename:
                    print(filename)
                    print('=' * len(filename))
                    printed_filename = True
                print(command[0])
                print('-' * len(command[0]))
                print(output)
                retcode |= proc.returncode

    return retcode


def load_conf():
    """ Load configuration parameters from the conf file """
    if os.path.exists(CONF_FILE):
        with open(CONF_FILE, 'r') as infile:
            return json.load(infile)
    else:
        return {}


def copy_index(tmpdir):
    """ Copy the git repo's index into a temporary directory """
    # Put the code being checked-in into the temp dir
    subprocess.check_call(['git', 'checkout-index', '-a', '-f', '--prefix=%s/'
                           % tmpdir])

    # Go to each recursive submodule and use a 'git archive' tarpipe to copy
    # the correct ref into the temporary directory
    output = check_output(['git', 'submodule', 'status', '--recursive',
                           '--cached'])
    for line in output.splitlines():
        ref, path, _ = line.split()
        ref = ref.strip('+')
        with pushd(path):
            archive = subprocess.Popen(['git', 'archive', '--format=tar', ref],
                                       stdout=subprocess.PIPE)
            untar_cmd = ['tar', '-x', '-C', '%s/%s/' % (tmpdir, path)]
            untar = subprocess.Popen(untar_cmd, stdin=archive.stdout,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT)
            out = untar.communicate()[0]
            if untar.returncode != 0:
                raise subprocess.CalledProcessError(untar.returncode,
                                                    untar_cmd, out)


def precommit(exit=True):
    """ Run all the pre-commit checks """
    tmpdir = tempfile.mkdtemp()

    try:
        copy_index(tmpdir)

        modified = check_output(['git', 'diff', '--cached', '--name-only',
                                 '--diff-filter=ACMRT'])
        modified = [name.strip() for name in modified.splitlines()]
        path = os.environ['PATH']
        with pushd(tmpdir) as prevdir:
            conf = load_conf()
            # Activate the virtualenv before running checks
            if 'env' in conf:
                binpath = os.path.abspath(os.path.join(prevdir,
                                                       conf['env']['path'],
                                                       'bin'))
                if binpath not in path.split(os.pathsep):
                    path = binpath + os.pathsep + path
            retcode = run_checks(conf.get('hooks_all', []),
                                 conf.get('hooks_modified', []), modified,
                                 path)

        if exit:
            sys.exit(retcode)
        else:
            return retcode
    finally:
        shutil.rmtree(tmpdir)

if __name__ == '__main__':
    precommit()
