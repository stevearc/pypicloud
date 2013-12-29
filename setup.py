""" Setup file """
import os
import sys

from setuptools import setup, find_packages
from version_helper import git_version


HERE = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(HERE, 'README.rst')).read()
CHANGES = open(os.path.join(HERE, 'CHANGES.rst')).read()

REQUIREMENTS = [
    'pyramid==1.4',
    'boto',
    'mock',
    'pyramid_jinja2',
    'paste',
    'passlib',
    'pyramid_tm',
    'redis',
    'transaction',
    'zope.sqlalchemy',
]

if sys.version_info[:2] < (2, 7):
    REQUIREMENTS.extend(['argparse', 'unittest2'])

if __name__ == "__main__":
    setup(
        name='pypicloud',
        description='Private PyPI backed by S3',
        long_description=README + '\n\n' + CHANGES,
        classifiers=[
            'Programming Language :: Python',
            'Programming Language :: Python :: 2.6',
            'Programming Language :: Python :: 2.7',
            'Development Status :: 4 - Beta',
            'Framework :: Pylons',
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
                'pypicloud-create-schema = pypicloud.scripts:run_create_schema',
                'pypicloud-drop-schema = pypicloud.scripts:run_drop_schema',
                'pypicloud-refresh-packages = pypicloud.scripts:run_refresh_packages',
            ],
            'paste.app_factory': [
                'main = pypicloud:main',
            ],
        },
        install_requires=REQUIREMENTS,
        tests_require=REQUIREMENTS,
        **git_version()
    )
