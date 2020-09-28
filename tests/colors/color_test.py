#!/usr/bin/env python3

import logging
import unittest

import coloredlogs

from lifxdev.colors import color


class ColorTest(unittest.TestCase):
    def test_rgba2hsbk(self):
        kelvin = 5500

        # Red
        rgb = color.Rgb(red=1, green=0, blue=0, norm=1)
        hsbk = color.Hsbk(hue=0, saturation=1, brightness=1, kelvin=kelvin)
        self._compare_colorconv(rgb, hsbk)

        # Green
        rgb = color.Rgb(red=0, green=1, blue=0, norm=1)
        hsbk = color.Hsbk(hue=120, saturation=1, brightness=1, kelvin=kelvin)
        self._compare_colorconv(rgb, hsbk)

        # Blue
        rgb = color.Rgb(red=0, green=0, blue=1, norm=1)
        hsbk = color.Hsbk(hue=240, saturation=1, brightness=1, kelvin=kelvin)
        self._compare_colorconv(rgb, hsbk)

        # White
        rgb = color.Rgb(red=1, green=1, blue=1, norm=1)
        hsbk = color.Hsbk(hue=0, saturation=0, brightness=1, kelvin=kelvin)
        self._compare_colorconv(rgb, hsbk)

    def _compare_colorconv(self, rgb: color.Rgb, hsbk: color.Hsbk):
        converted = color.rgba2hsbk(rgb, hsbk.kelvin)
        self.assertEqual(converted.hue, hsbk.hue)

    def test_from_tuple(self):
        hsbk_in = (300, 1, 1, 5500)
        hsbk_out = color.Hsbk.from_tuple(hsbk_in)
        self.assertEqual(hsbk_in[0], hsbk_out.hue)
        self.assertEqual(hsbk_in[1], hsbk_out.saturation)
        self.assertEqual(hsbk_in[2], hsbk_out.brightness)
        self.assertEqual(hsbk_in[3], hsbk_out.kelvin)


if __name__ == "__main__":
    coloredlogs.install(level=logging.INFO)
    unittest.main()
