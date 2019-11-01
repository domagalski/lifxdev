#!/usr/bin/env python3

import glob
from distutils.core import setup

pkg_name = "lifxdev"
setup(
    name=pkg_name,
    version="0.1.0",
    description="LIFX device control over LAN.",
    author="Rachel Simone Domagalski",
    author_email="rsdomagalski@gmail.com",
    license="GPL",
    packages=[pkg_name],
    scripts=glob.glob("scripts/*"),
)
