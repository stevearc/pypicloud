""" Setup file """
import sys

from setuptools import setup, find_packages

import os
import re


HERE = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(HERE, 'README.rst')).read()
CHANGES = open(os.path.join(HERE, 'CHANGES.rst')).read()
# Remove custom RST extensions for pypi
CHANGES = re.sub(r'\(\s*:(issue|pr|sha):.*?\)', '', CHANGES)
CHANGES = re.sub(r':ref:`(.*?) <.*>`', r'\1', CHANGES)

REQUIREMENTS = [
    'boto',
    'distlib>=0.2.0',
    'paste',
    'passlib',
    'pycrypto',
    'pyramid',
    'pyramid_beaker',
    'pyramid_duh>=0.1.1',
    'pyramid_jinja2',
    'pyramid_tm',
    'rsa',
    'six',
    'transaction',
    'zope.sqlalchemy',
]

TEST_REQUIREMENTS = [
    'flywheel',
    'mock',
    'moto',
    'nose',
    'redis',
    'requests',
    'webtest',
]

if sys.version_info[:2] < (2, 7):
    REQUIREMENTS.append('argparse')
    TEST_REQUIREMENTS.append('unittest2')

if __name__ == "__main__":
    setup(
        name='pypicloud',
        version='0.4.0',
        description='Private PyPI backed by S3',
        long_description=README + '\n\n' + CHANGES,
        classifiers=[
            'Programming Language :: Python',
            'Programming Language :: Python :: 2',
            'Programming Language :: Python :: 2.6',
            'Programming Language :: Python :: 2.7',
            'Development Status :: 4 - Beta',
            'Framework :: Pyramid',
            'Intended Audience :: System Administrators',
            'Intended Audience :: Developers',
            'License :: OSI Approved :: MIT License',
            'Topic :: Internet :: WWW/HTTP',
            'Topic :: System :: Systems Administration',
        ],
        license='MIT',
        author='Steven Arcangeli',
        author_email='stevearc@stevearc.com',
        url='http://pypicloud.readthedocs.org/',
        keywords='pypi s3 cheeseshop package',
        platforms='any',
        zip_safe=False,
        include_package_data=True,
        packages=find_packages(exclude=('tests',)),
        entry_points={
            'console_scripts': [
                'pypicloud-gen-password = pypicloud.scripts:gen_password',
                'pypicloud-make-config = pypicloud.scripts:make_config',
                'ppc-gen-password = pypicloud.scripts:gen_password',
                'ppc-make-config = pypicloud.scripts:make_config',
                'ppc-migrate = pypicloud.scripts:migrate_packages',
                'ppc-export = pypicloud.scripts:export_access',
                'ppc-import = pypicloud.scripts:import_access',
            ],
            'paste.app_factory': [
                'main = pypicloud:main',
            ],
        },
        install_requires=REQUIREMENTS,
        tests_require=REQUIREMENTS + TEST_REQUIREMENTS,
        test_suite='tests',
        extras_require={
            'ldap': ['python-ldap >= 2.4.0'],
            'server': ['waitress'],
            'dynamo': ['flywheel >= 0.2.0'],
        },
    )
