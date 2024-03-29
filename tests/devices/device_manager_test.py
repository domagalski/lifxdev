#!/usr/bin/env python3

import logging
import pathlib
import unittest
from typing import cast

import coloredlogs

from lifxdev.colors import color
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
            comm_init=lambda: self.mock_socket,
            config_path=CONFIG_PATH,
        )

    def test_get_devices(self):
        response = self.lifx.get_devices_on_network()
        self.assertIsNotNone(response)
        state_service = cast(list[packet.LifxResponse], response)[0].payload
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

    def test_set_color(self):
        hsbk = color.Hsbk(hue=300, saturation=1, brightness=1, kelvin=5500)
        for device in self.lifx.get_all_devices().values():
            device.set_color(hsbk)
            device_hsbk = device.get_color()
            self.assertEqual(round(device_hsbk.hue), round(hsbk.hue))
            self.assertEqual(device_hsbk.saturation, hsbk.saturation)
            self.assertAlmostEqual(device_hsbk.brightness, device.max_brightness, 4)
            self.assertEqual(device_hsbk.kelvin, hsbk.kelvin)

    def test_set_colormap(self):
        colors = [color.Hsbk.from_tuple((0, 0, 1, 5500)) for _ in range(16)]
        for device in self.lifx.get_all_devices().values():
            if isinstance(device, multizone.LifxMultiZone):
                device.set_multizone(colors)

        self.lifx.root.set_colormap("hsv")
        for device in self.lifx.get_all_devices().values():
            if not isinstance(device, (multizone.LifxMultiZone, tile.LifxTile)):
                hsbk = device.get_color()
                self.assertGreaterEqual(hsbk.brightness, 0.975)

    def test_set_power(self):
        self.lifx.root.set_power(True)
        for device in self.lifx.get_all_devices().values():
            self.assertTrue(device.get_power())

    def test_max_brightness(self):
        for label in ["device-a", "device-b", "device-c", "device-d"]:
            dev = self.lifx.get_device(label)
            self.assertEqual(dev.max_brightness, 1.0)

        for label in ["device-e", "device-f", "device-g"]:
            dev = self.lifx.get_device(label)
            self.assertEqual(dev.max_brightness, 0.5)
            if not isinstance(dev, (multizone.LifxMultiZone, tile.LifxTile)):
                continue

            dev.set_colormap("cool")
            if isinstance(dev, multizone.LifxMultiZone):
                self._check_mz(dev)
            elif isinstance(dev, tile.LifxTile):
                self._check_tile(dev)

    def _check_mz(self, dev: multizone.LifxMultiZone):
        zones = dev.get_multizone()
        for hsbk in zones:
            self.assertLessEqual(hsbk.brightness, dev.max_brightness)

    def _check_tile(self, dev: tile.LifxTile):
        tile_colors = dev.get_tile_colors(0)
        for color_list in tile_colors:
            for hsbk in color_list:
                self.assertLessEqual(hsbk.brightness, dev.max_brightness)


if __name__ == "__main__":
    coloredlogs.install(level=logging.INFO)
    unittest.main()
