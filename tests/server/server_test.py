#!/usr/bin/env python3

import json
import logging
import pathlib
import unittest
import threading
import time
from typing import Callable, Union

import portpicker

from lifxdev.server import logs
from lifxdev.server import client
from lifxdev.server import process
from lifxdev.server import server
from lifxdev.messages import test_utils


DEVICE_CONFIG = pathlib.Path(__file__).parent / "test_data" / "devices.yaml"
PROCESS_CONFIG = pathlib.Path(__file__).parent / "test_data" / "processes.yaml"


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.port = portpicker.pick_unused_port()
        self.mock_socket = test_utils.MockSocket()
        self.lifx_server = server.LifxServer(
            self.port,
            device_config_path=DEVICE_CONFIG,
            process_config_path=PROCESS_CONFIG,
            comm_init=lambda: self.mock_socket,
            timeout=5,
        )
        self.lifx_client = client.LifxClient(port=self.port, timeout=5, connect=False)

    def tearDown(self):
        self.assertTrue(self.run_cmd_get_response("killall", self.lifx_client))
        self.lifx_server.close()

    def run_cmd_get_response(
        self,
        cmd_str: str,
        call_func: Callable,
    ) -> Union[str, server.ServerResponse]:

        server = threading.Thread(target=self.lifx_server.recv_and_run)
        server.start()

        self.lifx_client.connect()
        try:
            response = call_func(cmd_str)
        except Exception as e:
            logs.log_exception(e, logging.critical)
            raise
        finally:
            server.join()
            self.lifx_client.close()
        return response

    def test_bad_command(self):
        self.assertRaises(
            server.UnknownServerCommand,
            self.run_cmd_get_response,
            "some-random-command device arg arg arg",
            self.lifx_client,
        )

    def test_on_off(self):
        self.assertTrue(self.run_cmd_get_response("off -h", self.lifx_client))
        self.assertTrue(self.run_cmd_get_response("on -h", self.lifx_client))

        self.assertTrue(self.run_cmd_get_response("on", self.lifx_client))
        response = self.run_cmd_get_response(
            "power device-a --machine",
            self.lifx_client.send_recv,
        )
        self.assertIsNone(response.error)
        self.assertEqual(response.response, "1")

        self.assertTrue(self.run_cmd_get_response("off", self.lifx_client))
        response = self.run_cmd_get_response(
            "power device-a --machine",
            self.lifx_client.send_recv,
        )
        self.assertIsNone(response.error)
        self.assertEqual(response.response, "0")

    @unittest.skip("currently broken")
    def test_client(self):
        self.assertRaises(
            SystemExit,
            self.run_cmd_get_response,
            ["-p", str(self.port), "-t", "5", "help"],
            client.main,
        )
        self.assertRaises(
            SystemExit,
            client.main,
            ["-p", str(self.port), "-t", "5"],
        )
        self.assertRaises(
            SystemExit,
            self.run_cmd_get_response,
            ["-p", str(self.port), "-t", "5", "help", "help"],
            client.main,
        )

    def test_help_commands(self):
        self.assertIn("\n", self.run_cmd_get_response("help", self.lifx_client))
        self.assertIn("\n", self.run_cmd_get_response("devices", self.lifx_client))
        self.assertIn("\n", self.run_cmd_get_response("groups", self.lifx_client))
        self.assertIn("\n", self.run_cmd_get_response("cmap", self.lifx_client))
        self.assertIn("\n", self.run_cmd_get_response("list", self.lifx_client))

        # Check machine-readable device/group information
        self.assertIn(
            "device-a",
            json.loads(self.run_cmd_get_response("devices --to-json", self.lifx_client)),
        )
        self.assertIn(
            "group-a",
            json.loads(self.run_cmd_get_response("groups --to-json", self.lifx_client))["groups"],
        )

        # Check specific devices
        self.assertIn(
            "Type: LifxLight", self.run_cmd_get_response("devices device-a", self.lifx_client)
        )
        device_attr = json.loads(
            self.run_cmd_get_response("devices device-a --to-json", self.lifx_client)
        )
        self.assertEqual("LifxLight", device_attr["device-a"]["type"])

        device_attr = json.loads(
            self.run_cmd_get_response("groups group-b --to-json", self.lifx_client)
        )
        self.assertEqual("LifxLight", device_attr["device-a"]["type"])

    def test_reload_config(self):
        self.assertIsNone(self.run_cmd_get_response("reload", self.lifx_client.send_recv).error)
        self.assertIsNone(
            self.run_cmd_get_response("reload device", self.lifx_client.send_recv).error
        )
        self.assertIsNone(
            self.run_cmd_get_response("reload process", self.lifx_client.send_recv).error
        )

    def test_set_color(self):
        logging.info(self.run_cmd_get_response("color -h", self.lifx_client))
        self.assertTrue(self.run_cmd_get_response("color all 300 0 0", self.lifx_client))
        self.assertTrue(self.run_cmd_get_response("color device-a", self.lifx_client))
        self.assertRaises(
            server.UnknownServerCommand,
            self.run_cmd_get_response,
            "color all",
            self.lifx_client,
        )
        # self.assertTrue(self.run_cmd_get_response("color device-a --machine", self.lifx_client))

    def test_set_colormap(self):
        logging.info(self.run_cmd_get_response("cmap -h", self.lifx_client))
        self.assertTrue(self.run_cmd_get_response("cmap all cool", self.lifx_client))
        self.assertRaises(
            server.InvalidDeviceError,
            self.run_cmd_get_response,
            "cmap device-a cool",
            self.lifx_client,
        )
        self.assertTrue(self.run_cmd_get_response("cmap device-d cool", self.lifx_client))

    def test_set_power(self):
        self.assertTrue(self.run_cmd_get_response("power -h", self.lifx_client))
        self.assertTrue(self.run_cmd_get_response("power all on", self.lifx_client))
        response = self.run_cmd_get_response("power device-a", self.lifx_client.send_recv)
        self.assertIsNone(response.error)
        self.assertTrue(response.response.endswith(" on"))

        response = self.run_cmd_get_response(
            "power device-a --machine",
            self.lifx_client.send_recv,
        )
        self.assertIsNone(response.error)
        self.assertEqual(response.response, "1")

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
            "power device-a --machine",
            self.lifx_client.send_recv,
        )
        self.assertIsNone(response.error)
        self.assertEqual(response.response, "0")

        self.assertRaises(
            server.UnknownServerCommand,
            self.run_cmd_get_response,
            "power group-a",
            self.lifx_client,
        )

    def test_start_stop(self):
        self.assertTrue(self.run_cmd_get_response("start -h", self.lifx_client))
        self.assertTrue(self.run_cmd_get_response("stop -h", self.lifx_client))

        # Check that a process is running
        self.assertTrue(self.run_cmd_get_response("start ongoing", self.lifx_client))
        self.assertIn(
            "Running processes:",
            self.run_cmd_get_response("list", self.lifx_client.send_recv).response,
        )
        self.assertTrue(self.run_cmd_get_response("stop ongoing", self.lifx_client))

        # Try starting a process twice
        self.assertTrue(self.run_cmd_get_response("start ongoing", self.lifx_client))
        self.assertRaises(
            process.ProcessRunningError,
            self.run_cmd_get_response,
            "start ongoing",
            self.lifx_client,
        )

        # Restart a process, then stop it.
        self.assertTrue(self.run_cmd_get_response("restart ongoing", self.lifx_client))
        self.assertIn(
            "No processes with errors",
            self.run_cmd_get_response("check", self.lifx_client.send_recv).response,
        )
        self.assertEqual(
            1, int(self.run_cmd_get_response("status ongoing --machine", self.lifx_client))
        )
        self.assertIn("is running", self.run_cmd_get_response("status ongoing", self.lifx_client))
        self.assertTrue(self.run_cmd_get_response("stop ongoing", self.lifx_client))
        self.assertEqual(
            0, int(self.run_cmd_get_response("status ongoing --machine", self.lifx_client))
        )
        self.assertIn(
            "is not running", self.run_cmd_get_response("status ongoing", self.lifx_client)
        )

        # check machine-readable list
        self.assertTrue(self.run_cmd_get_response("start oneshot", self.lifx_client))
        running = json.loads(self.run_cmd_get_response("list --to-json", self.lifx_client))[
            "running"
        ]
        self.assertIn("oneshot", running)

        # Handle long-running oneshot commands
        self.assertTrue(self.run_cmd_get_response("start really-long-oneshot", self.lifx_client))
        running = json.loads(self.run_cmd_get_response("list --to-json", self.lifx_client))[
            "running"
        ]
        self.assertIn("really-long-oneshot", running)
        self.assertFalse(json.loads(self.run_cmd_get_response("check --to-json", self.lifx_client)))
        failed_processes = json.loads(
            self.run_cmd_get_response("check --to-json --kill-oneshot", self.lifx_client)
        )
        self.assertIn("really-long-oneshot", failed_processes)

        # Detect errors
        timeout = 5
        sleep = 0.01
        for cmd in ["list", "check"]:
            self.assertTrue(self.run_cmd_get_response("start failure", self.lifx_client))
            detected_failure = False
            start = time.time()
            while time.time() < start + timeout:
                if "failure returncode: " in self.run_cmd_get_response(cmd, self.lifx_client):
                    detected_failure = True
                    break
                else:
                    time.sleep(sleep)

            self.assertTrue(detected_failure)


if __name__ == "__main__":
    logs.setup()
    unittest.main()
