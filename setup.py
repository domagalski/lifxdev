#!/usr/bin/env python3

import glob
from distutils.core import setup

pkg_name = "lifxdev"
setup(
    name=pkg_name,
    version="0.2.0",
    description="LIFX device control over LAN.",
    author="Rachel Simone Domagalski",
    license="GPL",
    packages=[pkg_name],
    scripts=glob.glob("scripts/*"),
)
