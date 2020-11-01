#!/usr/bin/env python3

import logging
import unittest

import coloredlogs

from lifxdev.colors import color
from lifxdev.devices import light
from lifxdev.messages import packet
from lifxdev.messages import test_utils


class LightTest(unittest.TestCase):
    def setUp(self):
        self.lifx = light.LifxInfraredLight(
            "127.0.0.1",
            label="LIFX mock",
            nonblock_delay=0,
            comm_init=lambda: test_utils.MockSocket(product=test_utils.Product.LIGHT),
        )

    def test_set_color(self):
        hsbk = color.Hsbk(hue=300, saturation=1, brightness=1, kelvin=5500)
        self.assertIsNotNone(self.lifx.set_color(hsbk, ack_required=True))
        response = self.lifx.get_color()
        self.assertAlmostEqual(round(hsbk.hue), round(response.hue))
        self.assertAlmostEqual(hsbk.saturation, response.saturation)
        self.assertAlmostEqual(hsbk.brightness, response.brightness)
        self.assertEqual(hsbk.kelvin, response.kelvin)

    def test_set_infrared(self):
        self.assertIsInstance(self.lifx.set_infrared(1.0, ack_required=True), packet.LifxResponse)
        ir_level = self.lifx.get_infrared()
        self.assertAlmostEqual(ir_level, 1.0)

    def test_set_power(self):
        self.assertIsInstance(self.lifx.set_power(True, ack_required=True), packet.LifxResponse)
        self.assertTrue(self.lifx.get_power())


if __name__ == "__main__":
    coloredlogs.install(level=logging.INFO)
    unittest.main()
