#!/usr/bin/env python3

import logging
import unittest

from lifxdev.messages import packet
from lifxdev.messages import light_messages


class LightMessageTest(unittest.TestCase):
    def test_set_color(self):
        # Green according to the LIFX packet tutorial:
        # https://lan.developer.lifx.com/docs/building-a-lifx-packet
        hsbk = packet.Hsbk()
        hsbk["hue"] = 21845  # Green
        hsbk["saturation"] = 65535
        hsbk["brightness"] = 65535
        hsbk["kelvin"] = 3500

        hsbk_bytes = hsbk.to_bytes()
        bytes_hex = [hex(bb) for bb in hsbk_bytes]
        bytes_int = [int(bb) for bb in hsbk_bytes]
        logging.info("HSBK green:")
        logging.info(hsbk_bytes)
        logging.info(bytes_hex)
        logging.info(bytes_int)

        color = light_messages.SetColor()
        color["color"] = hsbk
        color["duration"] = 1024

        color_bytes = color.to_bytes()
        color_hex = [hex(bb) for bb in color_bytes]
        color_int = [int(bb) for bb in color_bytes]
        logging.info("SetColor payload green:")
        logging.info(color_bytes)
        logging.info(color_hex)
        logging.info(color_int)
        nominal_payload = [
            0x00,
            0x55,
            0x55,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xAC,
            0x0D,
            0x00,
            0x04,
            0x00,
            0x00,
        ]
        self.assertEqual(color_int, nominal_payload)

        color_from_bytes = light_messages.SetColor.from_bytes(color_bytes)
        self.assertEqual(color_from_bytes["color"]["hue"], hsbk["hue"])
        self.assertEqual(color_from_bytes["color"]["saturation"], hsbk["saturation"])
        self.assertEqual(color_from_bytes["color"]["brightness"], hsbk["brightness"])
        self.assertEqual(color_from_bytes["color"]["kelvin"], hsbk["kelvin"])
        self.assertEqual(color_from_bytes["duration"], color["duration"])
        self.assertEqual(color_from_bytes.message_type, color.message_type)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    unittest.main()
