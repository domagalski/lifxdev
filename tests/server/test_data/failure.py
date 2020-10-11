#!/usr/bin/env python3

from lifxdev.server import server

print("Running failure test.")
raise server.CommandError("command failed")
