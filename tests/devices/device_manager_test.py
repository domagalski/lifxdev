#!/usr/bin/env python3

import logging
import pathlib
import unittest

import coloredlogs

from lifxdev.devices import device_manager
from lifxdev.devices import light
from lifxdev.devices import multizone
from lifxdev.devices import tile
from lifxdev.messages import packet
from lifxdev.messages import test_utils

CONFIG_PATH = pathlib.Path(__file__).parent / "test_data" / "devices.yaml"


class DeviceManagerTest(unittest.TestCase):
    def setUp(self):
        self.mock_socket = test_utils.MockSocket()
        self.lifx = device_manager.DeviceManager(
            verbose=True,
            nonblock_delay=0,
            comm=self.mock_socket,
            config_path=CONFIG_PATH,
        )

    def test_get_devices(self):
        state_service = self.lifx.get_devices_on_network()[0].payload
        self.assertEqual(state_service["port"], packet.LIFX_PORT)

    def test_get_label(self):
        label = "LIFX UnitTest Bulb"
        self.mock_socket.set_label(label)
        self.assertEqual(self.lifx.get_label("127.0.0.1"), label)

    def test_get_product_info(self):
        self.mock_socket.set_product(test_utils.Product.LIGHT)
        product_info = self.lifx.get_product_info("127.0.0.1")
        self.assertEqual(product_info["class"], light.LifxLight)

        self.mock_socket.set_product(test_utils.Product.IR)
        product_info = self.lifx.get_product_info("127.0.0.1")
        self.assertEqual(product_info["class"], light.LifxInfraredLight)

        self.mock_socket.set_product(test_utils.Product.MZ)
        product_info = self.lifx.get_product_info("127.0.0.1")
        self.assertEqual(product_info["class"], multizone.LifxMultiZone)

        self.mock_socket.set_product(test_utils.Product.TILE)
        product_info = self.lifx.get_product_info("127.0.0.1")
        self.assertEqual(product_info["class"], tile.LifxTile)

    def test_discovery(self):
        label = "LIFX UnitTest Bulb"
        self.mock_socket.set_label(label)
        self.mock_socket.set_product(test_utils.Product.LIGHT)

        devices = self.lifx.discover()
        self.assertEqual(len(devices), 1)
        self.assertIsInstance(devices[label].device, light.LifxLight)

    def test_load_config(self):
        # See the test data for the example group layout
        self.assertIsInstance(self.lifx.get_device("device-a"), light.LifxLight)
        self.assertIsInstance(self.lifx.get_device("device-b"), light.LifxInfraredLight)
        self.assertIsInstance(self.lifx.get_device("device-c"), multizone.LifxMultiZone)
        self.assertIsInstance(self.lifx.get_device("device-d"), tile.LifxTile)

        # Test that the groups are not in the devices
        self.assertFalse(self.lifx.has_device("group-a"))
        self.assertFalse(self.lifx.has_device("group-b"))

        self.assertTrue(self.lifx.has_group("group-b"))
        group_a = self.lifx.get_group("group-a")
        group_b = group_a.get_group("group-b")
        self.assertFalse(group_a.has_device("device-d"))
        self.assertFalse(group_b.has_group("group-b"))

        # Test bad configs
        for ii in range(1, 3 + 1):
            self.assertRaises(
                device_manager.DeviceConfigError,
                self.lifx.load_config,
                CONFIG_PATH.parent / f"bad_config{ii}.yaml",
            )


if __name__ == "__main__":
    coloredlogs.install(level=logging.INFO)
    unittest.main()
