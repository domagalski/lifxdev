#!/usr/bin/env python3

import setuptools

pkg_name = "lifxdev"
setuptools.setup(
    name=pkg_name,
    version="1.0.4",
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
)
