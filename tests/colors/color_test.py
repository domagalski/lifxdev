#!/usr/bin/env python3

import logging
import unittest

import coloredlogs

from lifxdev.colors import color


class ColorTest(unittest.TestCase):
    def test_from_tuple(self):
        hsbk_in = (300, 1, 1, 5500)
        hsbk_out = color.Hsbk.from_tuple(hsbk_in)
        self.assertEqual(hsbk_in[0], hsbk_out.hue)
        self.assertEqual(hsbk_in[1], hsbk_out.saturation)
        self.assertEqual(hsbk_in[2], hsbk_out.brightness)
        self.assertEqual(hsbk_in[3], hsbk_out.kelvin)

    def test_colormaps(self):
        all_cmaps = color.get_all_colormaps()
        self.assertIn("cool", all_cmaps)

        # color conversion check from known colormap
        hsbk = color.get_colormap("hsv", 1, 5500).pop()
        self.assertEqual(hsbk.hue, 0.0)
        self.assertEqual(hsbk.saturation, 1.0)
        self.assertEqual(hsbk.brightness, 1.0)

        # Check that bounds are equal regardless of array size
        hsbk_4 = color.get_colormap("viridis", 4, 5500)
        hsbk_8 = color.get_colormap("viridis", 8, 5500)
        self.assertEqual(hsbk_4[0], hsbk_8[0])
        self.assertEqual(hsbk_4[-1], hsbk_8[-1])


if __name__ == "__main__":
    coloredlogs.install(level=logging.INFO)
    unittest.main()
