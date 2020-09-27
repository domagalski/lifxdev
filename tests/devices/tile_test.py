#!/usr/bin/env python3

import logging
import unittest

import coloredlogs

from lifxdev.devices import light
from lifxdev.devices import tile
from lifxdev.messages import test_utils


class MultiZoneTest(unittest.TestCase):
    def setUp(self):
        self.lifx = tile.LifxTile.init_from_ip_addr(
            "127.0.0.1",
            nonblock_delay=0,
            comm=test_utils.MockSocket(product=test_utils.Product.MZ),
        )

    def test_get_device_chain(self):
        response = self.lifx.get_chain().payload
        tile_info = response["tile_devices"][0]
        self.assertTrue(tile_info["width"], tile.TILE_WIDTH)
        self.assertTrue(tile_info["height"], tile.TILE_WIDTH)

    def test_set_color(self):
        colors = [
            light.Hsbk(hue=5 * ii, saturation=1, brightness=1, kelvin=5500)
            for ii in range(tile.TILE_WIDTH ** 2)
        ]
        self.assertIsNotNone(self.lifx.set_tile_colors(0, colors, 0))
        recovered_colors = self.lifx.get_tile_colors(0)[0]

        self.assertEqual(len(colors), len(recovered_colors))
        for original, recovered in zip(colors, recovered_colors):
            self.assertAlmostEqual(round(original.hue), round(recovered.hue))
            self.assertAlmostEqual(original.saturation, recovered.saturation)
            self.assertAlmostEqual(original.brightness, recovered.brightness)
            self.assertEqual(original.kelvin, recovered.kelvin)


if __name__ == "__main__":
    coloredlogs.install(level=logging.INFO)
    unittest.main()
