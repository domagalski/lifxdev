#!/usr/bin/env python3

import logging
import unittest

import coloredlogs

from lifxdev.colors import color
from lifxdev.devices import tile
from lifxdev.messages import packet
from lifxdev.messages import test_utils


class MultiZoneTest(unittest.TestCase):
    def setUp(self):
        self.lifx = tile.LifxTile(
            "127.0.0.1",
            label="LIFX mock",
            nonblock_delay=0,
            comm_init=lambda: test_utils.MockSocket(product=test_utils.Product.TILE),
        )

    def test_get_device_chain(self):
        response = self.lifx.get_chain().payload
        self.assertEqual(response["total_count"], 5)
        for tile_info in response["tile_devices"]:
            self.assertEqual(tile_info["width"], tile.TILE_WIDTH)
            self.assertEqual(tile_info["height"], tile.TILE_WIDTH)

    def test_set_color(self):
        colors = [
            color.Hsbk(hue=5 * ii, saturation=1, brightness=1, kelvin=5500)
            for ii in range(tile.TILE_WIDTH ** 2)
        ]
        self.assertIsInstance(
            self.lifx.set_tile_colors(0, colors, ack_required=True), packet.LifxResponse
        )
        recovered_colors = self.lifx.get_tile_colors(0)[0]

        self.assertEqual(len(colors), len(recovered_colors))
        for original, recovered in zip(colors, recovered_colors):
            self.assertAlmostEqual(round(original.hue), round(recovered.hue))
            self.assertAlmostEqual(original.saturation, recovered.saturation)
            self.assertAlmostEqual(original.brightness, recovered.brightness)
            self.assertEqual(original.kelvin, recovered.kelvin)

        self.assertIsInstance(
            self.lifx.set_colormap("cool", ack_required=True), packet.LifxResponse
        )


if __name__ == "__main__":
    coloredlogs.install(level=logging.INFO)
    unittest.main()
