#!/usr/bin/env python3

import logging
import unittest

import coloredlogs

from lifxdev.devices import light
from lifxdev.messages import test_utils


class DeviceTest(unittest.TestCase):
    def setUp(self):
        self.lifx = light.LifxLight.init_from_ip_addr(
            "127.0.0.1",
            nonblock_delay=0,
            comm=test_utils.MockSocket(product=test_utils.Product.LIGHT),
        )

    def test_set_color(self):
        hsbk = light.Hsbk(hue=300, saturation=1, brightness=1, kelvin=5500)
        response = self.lifx.set_color(hsbk, 0)
        self.assertAlmostEqual(round(hsbk.hue), round(response.hue))
        self.assertAlmostEqual(hsbk.saturation, response.saturation)
        self.assertAlmostEqual(hsbk.brightness, response.brightness)
        self.assertEqual(hsbk.kelvin, response.kelvin)

    def test_set_infrared(self):
        ir_level = self.lifx.set_infrared(1.0)
        self.assertAlmostEqual(ir_level, 1.0)

    def test_set_power(self):
        self.lifx.set_power(True, 0)
        self.assertTrue(self.lifx.get_power())


if __name__ == "__main__":
    coloredlogs.install(level=logging.INFO)
    unittest.main()
