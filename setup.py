#!/usr/bin/env python3

# import glob
import setuptools

pkg_name = "lifxdev"
setuptools.setup(
    name=pkg_name,
    version="0.2.1",
    description="LIFX device control over LAN.",
    author="Rachel Simone Domagalski",
    license="GPL",
    packages=setuptools.find_namespace_packages(include=[f"{pkg_name}.*"]),
    package_data={"": ["*.yaml"]},
    # scripts=glob.glob("scripts/*"),
)
