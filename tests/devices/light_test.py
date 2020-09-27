#!/usr/bin/env python3

import logging
import unittest

import coloredlogs

from lifxdev.devices import light
from lifxdev.messages import test_utils


class LightTest(unittest.TestCase):
    def setUp(self):
        self.lifx = light.LifxInfraredLight.init_from_ip_addr(
            "127.0.0.1",
            nonblock_delay=0,
            comm=test_utils.MockSocket(product=test_utils.Product.LIGHT),
        )

    def test_rgba2hsbk(self):
        kelvin = 5500

        # Red
        rgba = light.Rgba(red=1, green=0, blue=0, norm=1)
        hsbk = light.Hsbk(hue=0, saturation=1, brightness=1, kelvin=kelvin)
        self._compare_colorconv(rgba, hsbk)

        # Green
        rgba = light.Rgba(red=0, green=1, blue=0, norm=1)
        hsbk = light.Hsbk(hue=120, saturation=1, brightness=1, kelvin=kelvin)
        self._compare_colorconv(rgba, hsbk)

        # Blue
        rgba = light.Rgba(red=0, green=0, blue=1, norm=1)
        hsbk = light.Hsbk(hue=240, saturation=1, brightness=1, kelvin=kelvin)
        self._compare_colorconv(rgba, hsbk)

        # White
        rgba = light.Rgba(red=1, green=1, blue=1, norm=1)
        hsbk = light.Hsbk(hue=0, saturation=0, brightness=1, kelvin=kelvin)
        self._compare_colorconv(rgba, hsbk)

    def _compare_colorconv(self, rgba: light.Rgba, hsbk: light.Hsbk):
        converted = light.rgba2hsbk(rgba, hsbk.kelvin)
        self.assertEqual(converted.hue, hsbk.hue)

    def test_set_color(self):
        hsbk = light.Hsbk(hue=300, saturation=1, brightness=1, kelvin=5500)
        self.assertIsNotNone(self.lifx.set_color(hsbk, 0))
        response = self.lifx.get_color()
        self.assertAlmostEqual(round(hsbk.hue), round(response.hue))
        self.assertAlmostEqual(hsbk.saturation, response.saturation)
        self.assertAlmostEqual(hsbk.brightness, response.brightness)
        self.assertEqual(hsbk.kelvin, response.kelvin)

    def test_set_infrared(self):
        self.assertIsNotNone(self.lifx.set_infrared(1.0))
        ir_level = self.lifx.get_infrared()
        self.assertAlmostEqual(ir_level, 1.0)

    def test_set_power(self):
        self.assertIsNotNone(self.lifx.set_power(True, 0))
        self.assertTrue(self.lifx.get_power())


if __name__ == "__main__":
    coloredlogs.install(level=logging.INFO)
    unittest.main()
