#!/usr/bin/env python

from setuptools import setup

setup(
    name="targetd",
    version="0.10.1",
    description="Linux remote storage API daemon",
    license="GPLv3",
    maintainer="Andy Grover",
    maintainer_email="andy@groveronline.com",
    url="http://github.com/open-iscsi/targetd",
    packages=["targetd", "targetd.backends"],
    install_requires=["setproctitle", "yaml", "rtslib_fb"],
    scripts=["scripts/targetd"],
)
