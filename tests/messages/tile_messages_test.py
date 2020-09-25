#!/usr/bin/env python3

import logging
import unittest

import coloredlogs

from lifxdev.messages import tile_messages
from lifxdev.messages import firmware_effects


class MultiZoneMessageTest(unittest.TestCase):
    def test_all_messages(self):
        """Test that registers are all valid"""
        logging.info(tile_messages.GetDeviceChain())
        logging.info(tile_messages.StateDeviceChain())
        logging.info(tile_messages.SetUserPosition())
        logging.info(tile_messages.GetTileState64())
        logging.info(tile_messages.SetTileState64())
        logging.info(tile_messages.StateTileState64())

    def test_firmware_effects(self):
        logging.info(firmware_effects.GetTileEffect())
        logging.info(firmware_effects.SetTileEffect())
        logging.info(firmware_effects.StateTileEffect())


if __name__ == "__main__":
    coloredlogs.install(level=logging.INFO)
    unittest.main()
