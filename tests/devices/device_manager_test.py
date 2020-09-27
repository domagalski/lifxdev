#!/usr/bin/env python3

import logging
import unittest

import coloredlogs

from lifxdev.devices import device_manager
from lifxdev.devices import light
from lifxdev.devices import multizone
from lifxdev.devices import tile
from lifxdev.messages import packet
from lifxdev.messages import test_utils


class DeviceManagerTest(unittest.TestCase):
    def setUp(self):
        self.lifx = device_manager.DeviceManager(
            nonblock_delay=0,
            comm=test_utils.MockSocket(),
        )

    def test_get_devices(self):
        state_service = self.lifx.get_devices()[0].payload
        self.assertEqual(state_service["port"], packet.LIFX_PORT)

    def test_get_label(self):
        label = "LIFX UnitTest Bulb"
        self.assertEqual(
            self.lifx.get_label(
                "127.0.0.1",
                comm=test_utils.MockSocket(label=label, product=test_utils.Product.LIGHT),
            ),
            label,
        )

    def test_get_product_info(self):
        product_info = self.lifx.get_product_info(
            "127.0.0.1", comm=test_utils.MockSocket(product=test_utils.Product.LIGHT)
        )
        self.assertEqual(product_info["class"], light.LifxLight)

        product_info = self.lifx.get_product_info(
            "127.0.0.1", comm=test_utils.MockSocket(product=test_utils.Product.IR)
        )
        self.assertEqual(product_info["class"], light.LifxInfraredLight)

        product_info = self.lifx.get_product_info(
            "127.0.0.1", comm=test_utils.MockSocket(product=test_utils.Product.MZ)
        )
        self.assertEqual(product_info["class"], multizone.LifxMultiZone)

        product_info = self.lifx.get_product_info(
            "127.0.0.1", comm=test_utils.MockSocket(product=test_utils.Product.TILE)
        )
        self.assertEqual(product_info["class"], tile.LifxTile)


if __name__ == "__main__":
    coloredlogs.install(level=logging.INFO)
    unittest.main()
