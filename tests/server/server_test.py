#!/usr/bin/env python3

import json
import logging
import pathlib
import unittest
import threading
import time
from collections.abc import Callable
from typing import cast

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
        )
        self.lifx_client = client.LifxClient(port=self.port, timeout=5)

    def tearDown(self):
        self.assertTrue(self.run_cmd_get_response("killall", self.lifx_client))
        self.lifx_server.close()

    def run_cmd_get_response(
        self,
        cmd_str: str,
        call_func: Callable,
    ) -> str | server.ServerResponse:
        def _wait_for_events(stop_request: threading.Event) -> None:
            while not stop_request.is_set():
                now_time = time.monotonic()
                self.lifx_server.recv_and_run(now_time)
                self.lifx_server.clear_stale_connections(now_time)

        stop_request = threading.Event()
        server = threading.Thread(target=_wait_for_events, args=(stop_request,))
        server.start()

        try:
            response = call_func(cmd_str)
        except Exception as e:
            logs.log_exception(e, logging.critical)
            raise
        finally:
            stop_request.set()
            server.join()
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
        self.assertIsInstance(response, server.ServerResponse)
        response = cast(server.ServerResponse, response)
        self.assertIsNone(response.error)
        self.assertEqual(response.response, "1")

        self.assertTrue(self.run_cmd_get_response("off", self.lifx_client))
        response = self.run_cmd_get_response(
            "power device-a --machine",
            self.lifx_client.send_recv,
        )
        response = cast(server.ServerResponse, response)
        self.assertIsNone(response.error)
        self.assertIsNone(response.error)
        self.assertEqual(response.response, "0")

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
        for cmd in ["help", "devices", "groups", "cmap", "list"]:
            response = self.run_cmd_get_response(cmd, self.lifx_client)
            self.assertIsInstance(response, str)
            response = cast(str, response)
            self.assertIn("\n", response)

        # Check machine-readable device/group information
        for cmd, expected, key in [
            ("devices --to-json", "device-a", None),
            ("groups --to-json", "group-a", "groups"),
        ]:
            response = self.run_cmd_get_response(cmd, self.lifx_client)
            self.assertIsInstance(response, str)
            response = cast(str, response)
            if key:
                self.assertIn(expected, json.loads(response)[key])
            else:
                self.assertIn(expected, json.loads(response))

        # Check specific devices
        for cmd, expected in [
            ("devices device-a", "Type: LifxLight"),
            ("groups group-b", "Device Group group-b"),
        ]:
            response = self.run_cmd_get_response(cmd, self.lifx_client)
            self.assertIsInstance(response, str)
            response = cast(str, response)
            self.assertIn(expected, response)

            response = self.run_cmd_get_response(f"{cmd} --to-json", self.lifx_client)
            self.assertIsInstance(response, str)
            response = cast(str, response)
            device_attr = json.loads(response)
            self.assertEqual("LifxLight", device_attr["device-a"]["type"])

    def test_reload_config(self):
        self.assertIsNone(
            cast(
                server.ServerResponse,
                self.run_cmd_get_response("reload", self.lifx_client.send_recv),
            ).error
        )
        self.assertIsNone(
            cast(
                server.ServerResponse,
                self.run_cmd_get_response("reload device", self.lifx_client.send_recv),
            ).error
        )
        self.assertIsNone(
            cast(
                server.ServerResponse,
                self.run_cmd_get_response("reload process", self.lifx_client.send_recv),
            ).error
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
        response = cast(
            server.ServerResponse,
            self.run_cmd_get_response("power device-a", self.lifx_client.send_recv),
        )
        self.assertIsNone(response.error)
        assert response.response  # for pyright
        self.assertTrue(response.response.endswith(" on"))

        response = cast(
            server.ServerResponse,
            self.run_cmd_get_response(
                "power device-a --machine",
                self.lifx_client.send_recv,
            ),
        )
        self.assertIsNone(response.error)
        assert response.response  # for pyright
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
        response = cast(
            server.ServerResponse,
            self.run_cmd_get_response(
                "power device-a --machine",
                self.lifx_client.send_recv,
            ),
        )
        self.assertIsNone(response.error)
        assert response.response  # for pyright
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
            cast(
                str,
                cast(
                    server.ServerResponse,
                    self.run_cmd_get_response("list", self.lifx_client.send_recv),
                ).response,
            ),
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
            cast(
                str,
                cast(
                    server.ServerResponse,
                    self.run_cmd_get_response("check", self.lifx_client.send_recv),
                ).response,
            ),
        )
        self.assertEqual(
            1,
            int(cast(str, self.run_cmd_get_response("status ongoing --machine", self.lifx_client))),
        )
        self.assertIn(
            "is running", cast(str, self.run_cmd_get_response("status ongoing", self.lifx_client))
        )
        self.assertTrue(self.run_cmd_get_response("stop ongoing", self.lifx_client))
        self.assertEqual(
            0,
            int(cast(str, self.run_cmd_get_response("status ongoing --machine", self.lifx_client))),
        )
        self.assertIn(
            "is not running",
            cast(str, self.run_cmd_get_response("status ongoing", self.lifx_client)),
        )

        # Handle long-running oneshot commands and test the command list json.
        self.assertTrue(self.run_cmd_get_response("start really-long-oneshot", self.lifx_client))
        running = json.loads(
            cast(str, self.run_cmd_get_response("list --to-json", self.lifx_client))
        )["running"]
        self.assertIn("really-long-oneshot", running)
        self.assertFalse(
            json.loads(cast(str, self.run_cmd_get_response("check --to-json", self.lifx_client)))
        )
        failed_processes = json.loads(
            cast(str, self.run_cmd_get_response("check --to-json --kill-oneshot", self.lifx_client))
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
                if "failure returncode: " in cast(
                    str, self.run_cmd_get_response(cmd, self.lifx_client)
                ):
                    detected_failure = True
                    break
                else:
                    time.sleep(sleep)

            self.assertTrue(detected_failure)


if __name__ == "__main__":
    logs.setup()
    unittest.main()
