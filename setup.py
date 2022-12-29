#!/usr/bin/env python3

import setuptools

pkg_name = "lifxdev"
setuptools.setup(
    name=pkg_name,
    version="1.4.3",
    description="LIFX device control over LAN.",
    author="Rachel Simone Domagalski",
    license="GPL",
    packages=setuptools.find_namespace_packages(include=[f"{pkg_name}.*"]),
    package_data={"": ["*.yaml"]},
    entry_points={
        "console_scripts": [
            "lifx-client=lifxdev.server.client:main",
            "lifx-server=lifxdev.server.server:main",
        ]
    },
    install_requires=[
        "click>=7.1",
        "coloredlogs>=15.0",
        "matplotlib>=3.6",
        "PyYAML>=5.3",
    ],
)
