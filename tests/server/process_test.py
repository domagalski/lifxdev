#!/usr/bin/env python3

import pathlib
import time
import unittest

from lifxdev.server import logs
from lifxdev.server import process


PROCESS_CONFIG = pathlib.Path(__file__).parent / "test_data" / "processes.yaml"


class ProcessTest(unittest.TestCase):
    def setUp(self):
        self.process_manager = process.ProcessManager(PROCESS_CONFIG)

    def tearDown(self):
        self.process_manager.killall(kill_immortal=True)

    def test_check_failures(self):
        failure_detected = False
        label = "failure"
        self.process_manager.start(label)

        start = time.time()
        while time.time() < start + 5:
            failures = self.process_manager.check_failures()
            time.sleep(0.01)
            if failures[label]:
                _, stderr = failures[label]
                failure_detected = "CommandError: command failed" in stderr
                break

        self.assertTrue(failure_detected)

    def test_get_avail_and_running(self):
        label = "ongoing"
        self.process_manager.start(label)

        available, running = self.process_manager.get_available_and_running()
        self.assertEqual(len(running), 1)

        self.process_manager.stop(label)

    def test_immortal(self):
        label = "immortal"
        self.process_manager.start(label)
        self.process_manager.killall()
        self.assertTrue(self.process_manager.get_process(label).running)
        self.process_manager.stop(label)

    def test_start_stop(self):
        label = "ongoing"
        self.process_manager.start(label)
        self.assertTrue(self.process_manager.get_process(label).running)
        self.assertRaises(process.ProcessRunningError, self.process_manager.start, label)
        self.process_manager.restart(label)
        self.process_manager.stop(label)
        # Stopping twice is fine. Nothing happens
        self.process_manager.stop(label)

        # Check oneshot commands aren't lingering.
        label = "oneshot"
        self.process_manager.start(label)
        self.assertFalse(self.process_manager.get_process(label).running)

        # Check conflicts
        label1 = "immortal"
        label2 = "ongoing"
        self.process_manager.start(label1)
        self.assertRaises(process.DeviceConflictError, self.process_manager.start, label2)
        self.process_manager.stop(label1)


if __name__ == "__main__":
    logs.setup()
    unittest.main()
