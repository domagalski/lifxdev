#!/usr/bin/env python3

import copy
import pathlib
import subprocess as spr
from typing import Dict, List, Optional, Set, Tuple, Union

import yaml


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
        filename: Union[str, pathlib.Path],
        *,
        devices: List[str] = [],
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

        self._proc: Optional[spr.Popen] = None
        self._running = False
        self._devices = set(devices)
        self._ongoing = ongoing
        self._immortal = immortal if ongoing else False

    @property
    def label(self) -> str:
        return self._label

    @property
    def running(self) -> bool:
        """Check if a process is running"""
        return bool(self._proc)

    @property
    def devices(self) -> Set:
        return copy.deepcopy(self._devices)

    @property
    def ongoing(self) -> bool:
        return self._ongoing

    @property
    def immortal(self) -> bool:
        return self._immortal

    def check_failure(self) -> Optional[Tuple[str, str]]:
        """Check that a running processes is still running.

        Return:
            If a process should be running but isn't, return (stdout, stderr) else None.
        """
        if not self._proc:
            return None

        retcode = self._proc.poll()
        if retcode is None:
            return None

        stdout, stderr = self._proc.communicate()
        self._proc = None
        return stdout, stderr

    def start(self, argv: List[str] = []) -> Optional[Tuple[str, str]]:
        """Start the process

        Return:
            If starting the process failed, return (stdout, stderr).
        """
        # Processes that are already running can't be duplicated.
        if self._proc and self._ongoing:
            raise ProcessRunningError(f"Process already running: {self._filename.name}")

        self._proc = spr.Popen(
            [self._filename] + argv,
            stdout=spr.PIPE,
            stderr=spr.PIPE,
            encoding="utf-8",
        )

        if not self._ongoing:
            stdout, stderr = self._proc.communicate()
            self._proc = None
            return stdout, stderr

    def stop(self) -> Optional[Tuple[str, str]]:
        """Stop the process"""
        if not self._proc:
            return

        self._proc.terminate()
        stdout, stderr = self._proc.communicate()
        self._proc = None
        return stdout, stderr


class ProcessManager:
    """Manage pre-defined processes."""

    def __init__(self, config_path: Union[str, pathlib.Path]):
        self._all_processes: Dict[str, Process] = {}

        self._config_path = pathlib.Path(config_path)
        if self._config_path.exists():
            self.load_config()

    def load_config(self, config_path: Optional[Union[str, pathlib.Path]] = None) -> None:
        """Load a config and setup the process manager.

        Args:
            config_path: (str) Path to the device config.
        """
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
        self._all_processes: Dict[str, Process] = {}
        for label, config in config_dict.items():
            filename = config.pop("filename", None)
            if filename:
                filename = proc_dir / filename
            else:
                raise ProcessConfigError(f"Process {label!r} has no filename.")

            self._all_processes[label] = Process(label, filename, **config)

    def get_process(self, label: str) -> Process:
        return self._all_processes[label]

    def has_process(self, label: str) -> bool:
        return label in self._all_processes

    def check_failure(self) -> Dict[str, Optional[Tuple[str, str]]]:
        """Check all processes for failures.

        Returns:
            Return a dict with labels and check_failure() for each process
        """
        failures: Dict[str, Optional[Tuple[str, str]]] = {}
        for label, process in self._all_processes.items():
            failures[label] = process.check_failure()
        return failures

    def killall(self) -> None:
        """Kill all processes except immortal processes"""
        for process in self._all_processes.values():
            if process.running and not process.immortal:
                process.stop()

    def restart(self, label: str, argv: List[str] = []) -> Optional[Tuple[str, str]]:
        """Start a process.

        Return:
            If starting the process failed, return (stdout, stderr).
        """
        self.stop(label)
        return self.start(label, argv)

    def start(self, label: str, argv: List[str] = []) -> Optional[Tuple[str, str]]:
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

        return process.start(argv)

    def stop(self, label: str) -> Optional[Tuple[str, str]]:
        """Stop the process"""
        process = self._all_processes[label]
        return process.stop()