# -*- coding: utf-8 -*-
from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand
from subprocess import call
import sys
import os
import json


with open(os.path.join('gpolygpx', 'version.json'), 'r') as jsonfile:
    version_file_content = jsonfile.read()
version = json.loads(version_file_content)['version']


INSTALL_REQUIRE = [
    'gpxpy',
    'polyline',
    'six',
    'invoke',
    'requests',
    'srtm.py',
    'haversine',
    'futures',
]


DEVELOP_REQUIRE = [
    'pytest',
    'pytest-cov',
    'sphinx',
    'tox',
    'repoze.sphinx.autointerface',
    'sphinx-rtd-theme',
    'ipdb',
    'ipython',
]


class PyTest(TestCommand):

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.pytest_args = []

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        sys.exit(call('py.test', shell=True))

setup(
    name='gpolygpx',
    version=version,
    description="Google polyline to GPX converter",
    long_description="""\ """,
    classifiers=[],  # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
    keywords='python GPX Google polyline',
    author='Ismaila Giroux',
    author_email='ismaila.giroux@gmail.com',
    url='https://github.com/igiroux/gpolygpx',
    license='GNU GPL',
    packages=find_packages(exclude=['examples', 'tests']),
    include_package_data=True,
    zip_safe=False,
    install_requires=INSTALL_REQUIRE,
    extras_require={
        'develop': DEVELOP_REQUIRE,
    },
    tests_require=['py.test', 'six'],
    cmdclass={'test': PyTest},
)
