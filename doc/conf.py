# -*- coding: utf-8 -*-
""" Sphinx config """
import sys
import importlib
import inspect
import os
import sphinx_rtd_theme
# pylint: disable=C0103
docs_basepath = os.path.abspath(os.path.dirname(__file__))

addtl_paths = (
    os.pardir,
    'extensions',
)

for path in addtl_paths:
    sys.path.insert(0, os.path.abspath(os.path.join(docs_basepath, path)))

extensions = ['sphinx.ext.autodoc', 'numpydoc', 'sphinx.ext.intersphinx',
              'sphinx.ext.linkcode', 'sphinx.ext.autosummary', 'github']

master_doc = 'index'
project = u'pypicloud'
copyright = u'2013, Steven Arcangeli'
github_user = u'mathcamp'

release = '0.2.7'
version = '.'.join(release.split('.')[:2])

exclude_patterns = ['_build']
pygments_style = 'sphinx'
html_theme = 'sphinx_rtd_theme'
html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]
numpydoc_show_class_members = False
intersphinx_mapping = {
    'python': ('http://docs.python.org/', None),
}


def linkcode_resolve(domain, info):
    """ Link source code to github """
    if domain != 'py' or not info['module']:
        return None
    filename = info['module'].replace('.', '/')
    mod = importlib.import_module(info['module'])
    basename = os.path.splitext(mod.__file__)[0]
    if basename.endswith('__init__'):
        filename += '/__init__'
    item = mod
    lineno = ''
    for piece in info['fullname'].split('.'):
        item = getattr(item, piece)
        try:
            lineno = '#L%d' % inspect.getsourcelines(item)[1]
        except (TypeError, IOError):
            pass
    return ("https://github.com/%s/%s/blob/%s/%s.py%s" %
            (github_user, project, release, filename, lineno))
