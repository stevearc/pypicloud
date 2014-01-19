""" Setup file """
import os
import sys

from setuptools import setup, find_packages
from pypicloud_version import git_version, UpdateVersion


HERE = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(HERE, 'README.rst')).read()
CHANGES = open(os.path.join(HERE, 'CHANGES.rst')).read()

REQUIREMENTS = [
    'boto',
    'paste',
    'passlib',
    'pycrypto',
    'pyramid',
    'pyramid_beaker',
    'pyramid_duh',
    'pyramid_jinja2',
    'pyramid_tm',
    'transaction',
    'zope.sqlalchemy',
]

TEST_REQUIREMENTS = []

if sys.version_info[:2] < (2, 7):
    REQUIREMENTS.extend(['argparse'])
    TEST_REQUIREMENTS.append('unittest2')

if __name__ == "__main__":
    setup(
        name='pypicloud',
        version=git_version('pypicloud'),
        cmdclass={'update_version': UpdateVersion},
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
        author_email='steven@highlig.ht',
        url='http://github.com/mathcamp/pypicloud',
        keywords='pypi s3 cheeseshop package',
        zip_safe=False,
        include_package_data=True,
        packages=find_packages(),
        entry_points={
            'console_scripts': [
                'pypicloud-gen-password = pypicloud.scripts:gen_password',
                'pypicloud-make-config = pypicloud.scripts:make_config',
                'pypicloud-create-schema = pypicloud.scripts:run_create_schema',
                'pypicloud-drop-schema = pypicloud.scripts:run_drop_schema',
            ],
            'paste.app_factory': [
                'main = pypicloud:main',
            ],
        },
        install_requires=REQUIREMENTS,
        tests_require=REQUIREMENTS + TEST_REQUIREMENTS,
    )
