#!/usr/bin/env python3

import logging
import unittest

import coloredlogs

from lifxdev.messages import multizone_messages
from lifxdev.messages import firmware_effects


class MultiZoneMessageTest(unittest.TestCase):
    def test_all_messages(self):
        """Test that registers are all valid"""
        logging.info(multizone_messages.SetExtendedColorZones())
        logging.info(multizone_messages.GetExtendedColorZones())
        logging.info(multizone_messages.StateExtendedColorZones())

    def test_firmware_effects(self):
        logging.info(firmware_effects.GetMultiZoneEffect())
        logging.info(firmware_effects.SetMultiZoneEffect())
        logging.info(firmware_effects.StateMultiZoneEffect())


if __name__ == "__main__":
    coloredlogs.install(level=logging.INFO)
    unittest.main()
