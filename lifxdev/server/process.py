#!/usr/bin/env python3

from __future__ import annotations

import pathlib
import subprocess as spr
import sys
import time

import yaml


CONFIG_PATH = pathlib.Path.home() / ".lifx" / "processes.yaml"


class DeviceConflictError(Exception):
    pass


class ProcessConfigError(Exception):
    pass


class ProcessRunningError(Exception):
    pass


class Process:
    """LIFX process class.

    This starts, stops, and logs a process defined in the LIFX process config
    """

    def __init__(
        self,
        label: str,
        filename: str | pathlib.Path,
        *,
        devices: list[str] = [],
        ongoing: bool = False,
        immortal: bool = False,
    ):
        """Create a process.

        Args:
            filename: (str) Path to the executable file.
            devices: (list) List of device labels.
            ongoing: (bool) If True, the process doesn't exit immediately.
            immortal: (bool) If True, the process manager can't kill it with killall.
        """
        self._label = label
        self._filename = pathlib.Path(filename)
        if not isinstance(devices, list):
            raise ValueError("devices must be a list.")
        if not isinstance(ongoing, bool):
            raise ValueError("ongoing must be a boolean.")
        if not isinstance(immortal, bool):
            raise ValueError("immortal must be a boolean.")

        self._cmd_args: list[str] | None = None
        self._proc: spr.Popen | None = None
        self._running = False
        self._devices = frozenset(devices)
        self._ongoing = ongoing
        self._immortal = immortal if ongoing else False

    @property
    def filename(self) -> pathlib.Path:
        return self._filename

    @property
    def label(self) -> str:
        return self._label

    @property
    def running(self) -> bool:
        """Check if a process is running"""
        if self._proc:
            return self._proc.poll() is None
        else:
            return False

    @property
    def devices(self) -> frozenset:
        return self._devices

    @property
    def ongoing(self) -> bool:
        return self._ongoing

    @property
    def immortal(self) -> bool:
        return self._immortal

    def check_failure(self) -> spr.CompletedProcess | None:
        """Check that a running processes is still running.

        Return:
            If a process should be running but isn't, return output else None.
        """
        if not self._proc:
            return None

        retcode = self._proc.poll()
        if retcode is None:
            return None

        completed = self.wait()
        if completed.returncode:
            return completed

    def kill(self) -> None:
        """Kill a process if possible."""
        if self._proc:
            if self._proc.poll() is None:
                # Do not reset self._proc to None so that check_failure can read it.
                self._proc.kill()
                # Wait until the process is fully killed before returning
                # Not using self._proc.wait() since it can deadlock with pipes.
                while self._proc.poll() is None:
                    time.sleep(0.001)

    def start(self, argv: list[str] = []) -> None:
        """Start the process"""
        # Processes that are already running can't be duplicated.
        # If the process, however, is not ongoing, cleanly stop before restarting.
        if self._proc:
            if self._ongoing and self._proc.poll() is None:
                raise ProcessRunningError(f"Process already running: {self._label}")
            else:
                self.stop()

        # Use the python executable running this for Process objects
        self._cmd_args = []
        if self._filename.name.endswith(".py"):
            self._cmd_args.append(sys.executable)
        self._cmd_args.append(str(self._filename))
        self._cmd_args += argv

        # Run the process.
        # Do not stop oneshot (non-ongoing processes). The ProcessManager handles that.
        self._proc = spr.Popen(self._cmd_args, stdout=spr.PIPE, stderr=spr.PIPE, encoding="utf-8")

    def stop(self) -> None:
        """Stop the process"""
        if not self._proc:
            return

        if self._proc.poll() is None:
            self._proc.kill()
        self._proc.communicate()
        self._proc = None

    def wait(self) -> spr.CompletedProcess:
        """Wait for the process to complete and return its output"""
        assert self._proc
        assert self._cmd_args
        stdout, stderr = self._proc.communicate()
        returncode = self._proc.returncode
        self._proc = None
        return spr.CompletedProcess(self._cmd_args, returncode, stdout.strip(), stderr.strip())


class ProcessManager:
    """Manage pre-defined processes."""

    def __init__(self, config_path: str | pathlib.Path = CONFIG_PATH):
        self._all_processes: dict[str, Process] = {}

        self._config_path = pathlib.Path(config_path)
        if self._config_path.exists():
            self.load_config()

    def load_config(self, config_path: str | pathlib.Path | None = None) -> None:
        """Load a config and setup the process manager.

        Any running process is stopped before a reload.

        Args:
            config_path: (str) Path to the device config.
        """
        self.killall(kill_immortal=True)

        config_path = pathlib.Path(config_path or self._config_path)
        with config_path.open() as f:
            config_dict = yaml.safe_load(f)

        # PROC_DIR is required.
        proc_dir = config_dict.pop("PROC_DIR", None)
        if proc_dir:
            proc_dir = config_path.parent / pathlib.Path(proc_dir)
        else:
            raise ProcessConfigError("Config file missing PROC_DIR.")

        # Load Process objects for everything in the config
        self._all_processes: dict[str, Process] = {}
        for label, config in config_dict.items():
            filename = config.pop("filename", None)
            if filename:
                filename = proc_dir / filename
            else:
                raise ProcessConfigError(f"Process {label!r} has no filename.")

            self._all_processes[label] = Process(label, filename, **config)

    def get_process(self, label: str) -> Process:
        """Get a process."""
        return self._all_processes[label]

    def has_process(self, label: str) -> bool:
        return label in self._all_processes

    def check_failures(self, *, kill_oneshot: bool = False) -> dict[str, spr.CompletedProcess]:
        """Check all processes for failures.

        Args:
            kill_oneshot: (bool) Kill any non-ongoing process that may be lingering.

        Returns:
            Return a dict with labels and check_failure() for each process
        """
        failures: dict[str, spr.CompletedProcess] = {}
        for label, process in self._all_processes.items():
            if not process.ongoing and kill_oneshot:
                process.kill()
            output = process.check_failure()
            if output:
                failures[label] = output
        return failures

    def get_available_and_running(self) -> tuple[list[Process], list[Process]]:
        """Get all processes.

        Returns:
            available_processes, running_processes
        """
        available_processes: list[Process] = []
        running_processes: list[Process] = []
        for label in self._all_processes:
            process = self.get_process(label)
            if process.running:
                running_processes.append(process)
            else:
                available_processes.append(process)
        return available_processes, running_processes

    def killall(self, kill_immortal: bool = False) -> None:
        """Kill all processes except immortal processes"""
        for process in self._all_processes.values():
            if kill_immortal or not process.immortal:
                process.stop()

    def restart(self, label: str, argv: list[str] = []) -> None:
        """Start a process.

        Return:
            If starting the process failed, return (stdout, stderr).
        """
        self.stop(label)
        self.start(label, argv)

    def start(self, label: str, argv: list[str] = []) -> None:
        """Start a process.

        Return:
            If starting the process failed, return (stdout, stderr).
        """
        process = self._all_processes[label]

        # Get all devices for all running processes
        all_devices = set()
        for plabel, proc in self._all_processes.items():
            if plabel == label:
                continue

            if not proc.running:
                continue

            all_devices |= proc.devices

        union = process.devices & all_devices
        if union:
            conflicts = ", ".join(union)
            raise DeviceConflictError(f"Devices in use: {conflicts}")

        process.start(argv)

    def stop(self, label: str) -> None:
        """Stop the process"""
        process = self._all_processes[label]
        process.stop()
