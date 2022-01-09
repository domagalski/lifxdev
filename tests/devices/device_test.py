#!/usr/bin/env python3

import logging
import unittest

import coloredlogs

from lifxdev.devices import device
from lifxdev.messages import test_utils


class DeviceTest(unittest.TestCase):
    def setUp(self):
        self.lifx = device.LifxDevice(
            "127.0.0.1",
            nonblock_delay=0,
            comm_init=lambda: test_utils.MockSocket(),
        )

    def test_set_power(self):
        self.assertIsNotNone(self.lifx.set_power(True, ack_required=True))
        self.assertTrue(self.lifx.get_power())


if __name__ == "__main__":
    coloredlogs.install(level=logging.INFO)
    unittest.main()
