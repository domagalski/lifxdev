#!/usr/bin/env python3

import logging
import unittest

import coloredlogs

from lifxdev.colors import color
from lifxdev.devices import multizone
from lifxdev.messages import packet
from lifxdev.messages import test_utils


class MultiZoneTest(unittest.TestCase):
    def setUp(self):
        self.lifx = multizone.LifxMultiZone(
            "127.0.0.1",
            nonblock_delay=0,
            comm=test_utils.MockSocket(product=test_utils.Product.MZ),
        )

    def test_set_multizone(self):
        colors = [
            color.Hsbk(hue=20 * ii, saturation=1, brightness=1, kelvin=5500) for ii in range(16)
        ]
        self.assertIsInstance(self.lifx.set_multizone(colors, 0), packet.LifxResponse)
        recovered_colors = self.lifx.get_multizone()
        self.assertEqual(len(colors), len(recovered_colors))
        for original, recovered in zip(colors, recovered_colors):
            self.assertAlmostEqual(round(original.hue), round(recovered.hue))
            self.assertAlmostEqual(original.saturation, recovered.saturation)
            self.assertAlmostEqual(original.brightness, recovered.brightness)
            self.assertEqual(original.kelvin, recovered.kelvin)


if __name__ == "__main__":
    coloredlogs.install(level=logging.INFO)
    unittest.main()
