#!/usr/bin/env python3

import logging
import unittest

import coloredlogs

from lifxdev.devices import device
from lifxdev.messages import packet
from lifxdev.messages import test_utils


class DeviceTest(unittest.TestCase):
    def setUp(self):
        self.lifx = device.LifxDevice.init_from_ip_addr(
            "127.0.0.1",
            nonblock_delay=0,
            comm=test_utils.MockSocket(),
        )

    def test_set_power(self):
        self.lifx.set_power(True)
        self.assertTrue(self.lifx.get_power())

    def test_get_device_info(self):
        state_service = self.lifx.get_device_info()[0].payload
        self.assertEqual(state_service["port"], packet.LIFX_PORT)


if __name__ == "__main__":
    coloredlogs.install(level=logging.INFO)
    unittest.main()
