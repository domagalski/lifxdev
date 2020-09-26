#!/usr/bin/env python3

import logging
import unittest

import coloredlogs

from lifxdev.messages import device_messages


class DeviceMessageTest(unittest.TestCase):
    def test_echo(self):
        msg = "hello there"
        echo = device_messages.EchoRequest(payload=msg)
        echo_bytes = echo.to_bytes()
        recovered = device_messages.EchoRequest.from_bytes(echo_bytes)
        logging.info(recovered)
        payload = recovered["payload"]
        self.assertEqual(msg, payload)

    def test_all_messages(self):
        """Test that registers are all valid"""
        logging.info(device_messages.GetService())
        logging.info(device_messages.StateService())
        logging.info(device_messages.GetHostInfo())
        logging.info(device_messages.StateHostInfo())
        logging.info(device_messages.GetHostFirmware())
        logging.info(device_messages.StateHostFirmware())
        logging.info(device_messages.GetWifiInfo())
        logging.info(device_messages.StateWifiInfo())
        logging.info(device_messages.GetPower())
        logging.info(device_messages.SetPower())
        logging.info(device_messages.StatePower())
        logging.info(device_messages.GetLabel())
        logging.info(device_messages.SetLabel())
        logging.info(device_messages.StateLabel())
        logging.info(device_messages.GetVersion())
        logging.info(device_messages.StateVersion())
        logging.info(device_messages.GetInfo())
        logging.info(device_messages.StateInfo())
        logging.info(device_messages.GetLocation())
        logging.info(device_messages.SetLocation())
        logging.info(device_messages.StateLocation())
        logging.info(device_messages.GetGroup())
        logging.info(device_messages.SetGroup())
        logging.info(device_messages.StateGroup())
        logging.info(device_messages.EchoRequest())
        logging.info(device_messages.EchoResponse())


if __name__ == "__main__":
    coloredlogs.install(level=logging.INFO)
    unittest.main()
