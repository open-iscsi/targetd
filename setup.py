#!/usr/bin/env python

from distutils.core import setup

setup(
    name = 'targetd',
    version = '0.7',
    description = 'Linux remote storage API daemon',
    license = 'GPLv3',
    maintainer = 'Andy Grover',
    maintainer_email = 'agrover@redhat.com',
    url = 'http://github.com/agrover/targetd',
    packages = ['targetd'],
    scripts = ['scripts/targetd'],
    )
