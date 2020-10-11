#!/usr/bin/env python3

from lifxdev.server import server

print("running oneshot command")
raise server.CommandError("exiting oneshot command")
