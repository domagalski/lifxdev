#!/usr/bin/env python3

import unittest
from typing import Tuple, List, Union, Callable

from lifxdev import util

KELVIN = 5500

_NUMBER = Union[int, float]
_COLOR_TUPLE = Tuple[_NUMBER, _NUMBER, _NUMBER, _NUMBER]
_COLOR = Union[List[_NUMBER], _COLOR_TUPLE]


class UtilTest(unittest.TestCase):
    def test_hsbk(self):
        # Basic input validation
        self.assertRaises(ValueError, util.hsbk_human, 32)
        self.assertRaises(ValueError, util.hsbk_human, (0, 0, 0))
        self.assertRaises(ValueError, util.hsbk_machine, 32)
        self.assertRaises(ValueError, util.hsbk_machine, (0, 0, 0))

        # Check the math
        machine = (0, 0, 0, KELVIN)
        human = (0, 0, 0, KELVIN)
        self._compare_hsbk(util.hsbk_human, machine, human)
        self._compare_hsbk(util.hsbk_machine, human, machine)

        # check numbers convert back and forth
        machine = (int(65535 / 5), int(2 * 65535 / 5), int(3 * 65535 / 5), KELVIN)
        human = (72, 0.4, 0.6, KELVIN)
        self._compare_hsbk(util.hsbk_human, machine, human)
        self._compare_hsbk(util.hsbk_machine, human, machine)

    def _compare_hsbk(
        self, converter: Callable[[_COLOR], _COLOR_TUPLE], hsbk: _COLOR, reference: _COLOR
    ):
        for i, val in enumerate(converter(hsbk)):
            self.assertEqual(reference[i], val)

    def test_is_str_type(self):
        self.assertTrue(util.is_str_ipaddr("127.0.0.1"))
        self.assertFalse(util.is_str_ipaddr("123.456.789.0"))
        self.assertFalse(util.is_str_ipaddr("AAAAAAAAAAAAAAA"))
        self.assertFalse(util.is_str_ipaddr("1.2.3."))

        self.assertTrue(util.is_str_mac("ff:ff:ff:ff:ff:ff"))
        self.assertFalse(util.is_str_mac("aaaaaaaaaaaaaaaaaaaa"))
        self.assertFalse(util.is_str_mac("ab:cd:ef:gh:ij:kl"))

    def test_conversions(self):
        self.assertEqual(util.mac_int_to_str(281474976710655), "ff:ff:ff:ff:ff:ff")
        self.assertEqual(util.mac_str_to_int("00:00:00:00:00:00"), 0)

        # Red
        rgba = (1, 0, 0, 1)
        hsbk = (0, 1, 1, KELVIN)
        self._compare_colorconv(util.rgba2hsbk, rgba, hsbk, KELVIN)

        # Green
        rgba = (0, 1, 0, 1)
        hsbk = (120, 1, 1, KELVIN)
        self._compare_colorconv(util.rgba2hsbk, rgba, hsbk, KELVIN)

        # Blue
        rgba = (0, 0, 1, 1)
        hsbk = (240, 1, 1, KELVIN)
        self._compare_colorconv(util.rgba2hsbk, rgba, hsbk, KELVIN)

        # White
        rgba = (1, 1, 1, 1)
        hsbk = (0, 0, 1, KELVIN)
        self._compare_colorconv(util.rgba2hsbk, rgba, hsbk, KELVIN)

        # White
        rgba = (1, 1, 1, 1)
        hsbk = (0, 0, 1, KELVIN)
        self._compare_colorconv(util.rgba2hsbk, rgba, hsbk, KELVIN)

        self.assertRaises(ValueError, util.rgba2hsbk, 32, KELVIN)
        self.assertRaises(ValueError, util.rgba2hsbk, (0, 0, 0), KELVIN)

    def _compare_colorconv(
        self,
        converter: Callable[[_COLOR, _NUMBER], _COLOR_TUPLE],
        input_color: _COLOR,
        reference: _COLOR,
        number: _NUMBER,
    ):
        for i, val in enumerate(converter(input_color, number)):
            self.assertEqual(reference[i], val)


if __name__ == "__main__":
    unittest.main()
