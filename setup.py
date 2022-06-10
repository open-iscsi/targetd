#!/usr/bin/env python

from distutils.core import setup

setup(
    name="targetd",
    version="0.10.0",
    description="Linux remote storage API daemon",
    license="GPLv3",
    maintainer="Andy Grover",
    maintainer_email="andy@groveronline.com",
    url="http://github.com/open-iscsi/targetd",
    packages=["targetd", "targetd.backends"],
    install_requires=["setproctitle", "PyYAML", "rtslib_fb"],
    scripts=["scripts/targetd"],
)
