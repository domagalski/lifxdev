#!/usr/bin/env python3

import copy
import pathlib
import subprocess as spr
import sys
from typing import Dict, List, Optional, Set, Tuple, Union

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
    def filename(self) -> pathlib.Path:
        return self._filename

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
        returncode = self._proc.returncode
        self._proc = None
        if returncode:
            return stdout, stderr

    def start(self, argv: List[str] = []) -> None:
        """Start the process"""
        # Processes that are already running can't be duplicated.
        # If the process, however, is not ongoing, cleanly stop before restarting.
        if self._proc:
            if self._ongoing:
                raise ProcessRunningError(f"Process already running: {self._label}")
            else:
                self.stop()

        # Use the python executable running this for Process objects
        cmd = []
        if self._filename.name.endswith(".py"):
            cmd.append(sys.executable)
        cmd.append(self._filename)
        cmd += argv

        # Run the process.
        # Do not stop oneshot (non-ongoing processes). The ProcessManager handles that.
        self._proc = spr.Popen(cmd, stdout=spr.PIPE, stderr=spr.PIPE, encoding="utf-8")

    def stop(self) -> None:
        """Stop the process"""
        if not self._proc:
            return

        if self._ongoing:
            self._proc.terminate()
        self._proc.communicate()
        self._proc = None


class ProcessManager:
    """Manage pre-defined processes."""

    def __init__(self, config_path: Union[str, pathlib.Path] = CONFIG_PATH):
        self._all_processes: Dict[str, Process] = {}

        self._config_path = pathlib.Path(config_path)
        if self._config_path.exists():
            self.load_config()

    def load_config(self, config_path: Optional[Union[str, pathlib.Path]] = None) -> None:
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
        self._all_processes: Dict[str, Process] = {}
        for label, config in config_dict.items():
            filename = config.pop("filename", None)
            if filename:
                filename = proc_dir / filename
            else:
                raise ProcessConfigError(f"Process {label!r} has no filename.")

            self._all_processes[label] = Process(label, filename, **config)

    def get_process(self, label: str) -> Process:
        """Get a process. If non-ongoing, make sure it's stopped first"""
        proc = self._all_processes[label]
        if not proc.ongoing:
            proc.stop()
        return proc

    def has_process(self, label: str) -> bool:
        return label in self._all_processes

    def check_failures(self) -> Dict[str, Optional[Tuple[str, str]]]:
        """Check all processes for failures.

        Returns:
            Return a dict with labels and check_failure() for each process
        """
        failures: Dict[str, Optional[Tuple[str, str]]] = {}
        for label, process in self._all_processes.items():
            failures[label] = process.check_failure()
        return failures

    def get_available_and_running(self) -> Tuple[List[Process], List[Process]]:
        """Get all processes.

        Returns:
            dict(label: available_processes), dict(label: running_processes)
        """
        available_processes: List[Process] = []
        running_processes: List[Process] = []
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
            if not process.immortal:
                process.stop()

    def restart(self, label: str, argv: List[str] = []) -> None:
        """Start a process.

        Return:
            If starting the process failed, return (stdout, stderr).
        """
        self.stop(label)
        self.start(label, argv)

    def start(self, label: str, argv: List[str] = []) -> None:
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
