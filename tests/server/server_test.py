#!/usr/bin/env python3

import logging
import pathlib
import unittest
import threading
from typing import Callable, Union

import portpicker

from lifxdev.server import logs
from lifxdev.server import client
from lifxdev.server import server
from lifxdev.messages import test_utils


DEVICE_CONFIG = pathlib.Path(__file__).parent / "test_data" / "devices.yaml"
PROCESS_CONFIG = pathlib.Path(__file__).parent / "test_data" / "processes.yaml"


class DeviceManagerTest(unittest.TestCase):
    def setUp(self):
        zmq_port = portpicker.pick_unused_port()
        self.mock_socket = test_utils.MockSocket()
        self.lifx_server = server.LifxServer(
            zmq_port,
            device_config_path=DEVICE_CONFIG,
            process_config_path=PROCESS_CONFIG,
            comm=self.mock_socket,
        )
        self.lifx_client = client.LifxClient(port=zmq_port)

    def run_cmd_get_response(
        self,
        cmd_str: str,
        call_func: Callable,
    ) -> Union[str, server.ServerResponse]:

        server = threading.Thread(target=self.lifx_server.recv_and_run)
        server.start()

        try:
            response = call_func(cmd_str)
        except Exception as e:
            logs.log_exception(e, logging.critical)
            raise
        finally:
            server.join()
        return response

    def test_bad_command(self):
        self.assertRaises(
            server.UnknownServerCommand,
            self.run_cmd_get_response,
            "some-random-command device arg arg arg",
            self.lifx_client,
        )

    def test_set_power(self):
        logging.info(self.run_cmd_get_response("power -h", self.lifx_client))
        logging.info(self.run_cmd_get_response("power all on", self.lifx_client))
        response = self.run_cmd_get_response("power device-a state", self.lifx_client.send_recv)
        self.assertIsNone(response.error)
        self.assertTrue(response.response.endswith(" on"))

        response = self.run_cmd_get_response(
            "power device-a state --machine",
            self.lifx_client.send_recv,
        )
        self.assertIsNone(response.error)
        self.assertEqual(response.response, "1")

        self.assertRaises(
            server.CommandError,
            self.run_cmd_get_response,
            "power device-a",
            self.lifx_client,
        )
        self.assertRaises(
            server.CommandError,
            self.run_cmd_get_response,
            "power device-a asdf",
            self.lifx_client,
        )
        self.assertRaises(
            server.InvalidDeviceError,
            self.run_cmd_get_response,
            "power some-random-device off",
            self.lifx_client,
        )

        logging.info(self.run_cmd_get_response("power group-a off", self.lifx_client))
        response = self.run_cmd_get_response(
            "power device-a state --machine",
            self.lifx_client.send_recv,
        )
        self.assertIsNone(response.error)
        self.assertEqual(response.response, "0")

        self.assertRaises(
            server.UnknownServerCommand,
            self.run_cmd_get_response,
            "power group-a state",
            self.lifx_client,
        )


if __name__ == "__main__":
    logs.setup()
    unittest.main()
