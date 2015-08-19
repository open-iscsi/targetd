#!/usr/bin/env python

from distutils.core import setup

setup(
    name = 'Konnector',
    version = '0.0.1',
    description = 'Linux remote storage API daemon',
    license = 'GPLv3',
    maintainer = 'Victor Brecheteau',
    maintainer_email = 'vb@mpstor.com',
    url = 'http://github.com/mpstor',
    packages = ['targetd'],
    scripts = ['scripts/targetd'],
    )
