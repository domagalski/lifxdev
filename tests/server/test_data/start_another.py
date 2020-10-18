#!/usr/bin/env python3

import sys

from lifxdev.server import client

port = int(sys.argv[1])
lifx = client.LifxClient(port=port)
print(lifx("restart ongoing"))
lifx.close()
