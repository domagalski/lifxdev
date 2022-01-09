#!/usr/bin/env python3

import argparse
import inspect
import json
import logging
import pathlib
import pickle
import random
import shlex
import socket
import threading
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Set, Type, Union

import click

from lifxdev.colors import color
from lifxdev.devices import device_manager
from lifxdev.devices import light
from lifxdev.devices import tile
from lifxdev.server import logs
from lifxdev.server import process

BUFFER_SIZE = 512
SERVER_PORT = 16384
SERVER_TIMEOUT = 60.0
DEVICE_CONFIG = device_manager.CONFIG_PATH
PROCESS_CONFIG = process.CONFIG_PATH


class CommandError(Exception):
    pass


class InvalidDeviceError(Exception):
    pass


class UnknownServerCommand(Exception):
    pass


class _CommandParser(argparse.ArgumentParser):
    def error(self, message):
        raise CommandError(message)


def _command(label: str, description: str) -> Callable:
    """Label a LifxServer class method as a command.

    Args:
        label: (str) Label of the function
        description: (str) Short description of the function.
    """

    def _server_command(function: Callable) -> Callable:
        # Apply a label and description
        function.label = label
        function.description = description

        # Construct the arg parser
        arg_list = []
        if hasattr(function, "arg_list"):
            arg_list = function.arg_list[:]
            del function.arg_list
        function.parser = _CommandParser(prog=label, description=description)
        for flags, kwargs in reversed(arg_list):
            function.parser.add_argument(*flags, **kwargs)

        return function

    return _server_command


def _is_command(item: Any) -> bool:
    """Return True if an object is a server command"""
    return all(
        [
            inspect.ismethod(item),
            hasattr(item, "label"),
            hasattr(item, "description"),
            hasattr(item, "parser"),
        ]
    )


def _add_arg(
    *flags,
    help_msg: str,
    arg_type: Type = str,
    default: Optional[Any] = None,
    required: bool = False,
    choices: Optional[Union[List, Set]] = None,
    nargs: Optional[Union[int, str]] = None,
) -> Callable:
    """Register argument parsing options to a server command

    Args:
        flags: Argument name. Must be the same as the function call.
        help_msg: Help message to display for an argument.
        arg_type: The data type to convert strings to.
        default: The default value of the argument.
        required: Whether or not the argument is required.
        choices: Iterable of valid choices for the argument.
        nargs: Specify the number or args using the argparse convention.
    """

    def _add_arg_to_method(function: Callable):
        if not hasattr(function, "arg_list"):
            function.arg_list = []

        kwargs: Dict[str, Any] = {"help": help_msg}
        if arg_type == bool:
            kwargs["action"] = "store_true"
        else:
            kwargs["default"] = default
            kwargs["type"] = arg_type
        if flags[0][0] == "-":
            kwargs["required"] = required
        if choices:
            kwargs["choices"] = choices
        if nargs:
            kwargs["nargs"] = nargs

        function.arg_list.append((flags, kwargs))
        return function

    return _add_arg_to_method


class ServerResponse(NamedTuple):
    response: Optional[str] = None
    error: Optional[Exception] = None


class _ThreadRunner:
    """Helper class to _ThreadPool to run threads"""

    def __init__(self, func: Callable, lock: threading.Lock):
        """Run a thread, managed by ThreadPool

        Args:
            func: A function that takes no arguments to run.
            lock: ThreadPool's lock to ensure only one thread runs at a time.
        """
        self._complete_lock = threading.Lock()
        self._complete = False

        self._lock = lock
        self._func = func
        self._thread = threading.Thread(target=self._run)
        self._thread.start()

    @property
    def complete(self) -> bool:
        """Check if the thread is complete"""
        with self._complete_lock:
            return self._complete

    @complete.setter
    def complete(self, state: bool) -> None:
        """Set whether the thread is complete"""
        with self._complete_lock:
            self._complete = state

    def _run(self) -> None:
        """Run a thread and mark it as complete"""
        with self._lock:
            self._func()
        self.complete = True

    def join(self) -> None:
        """Join the thread"""
        self._thread.join()


class _ThreadPool:
    """Create a basic thread pool for the LIFX server

    While the LIFX server supports only running one thread at a time,
    the thread pool helps queue up threads if incoming connections come
    in faster than the LIFX server can run a thread. After the maximum
    number of threads are reached and not all threads are complete,
    the thread pool will drop any incoming thread requests.

    This might be overkill and not necessary, but using it anyways.
    """

    def __init__(self, num_threads: int):
        """Create a thread pool and set the maximum number of threads"""
        self._lock = threading.Lock()
        self._num_threads = num_threads
        self._threads: Dict[int, _ThreadRunner] = {}

    def add(self, func: Callable):
        """Add a function to the thread pool.

        The function takes no args. If the thread pool is full, the
        function will not be run.
        """
        uid = random.randint(0, (1 << 32) - 1)
        while uid in self._threads:
            uid = random.randint(0, (1 << 32) - 1)

        if len(self._threads) == self._num_threads:
            for uid in list(self._threads.keys()):
                if self._threads[uid].complete:
                    self._threads.pop(uid).join()

        if len(self._threads) != self._num_threads:
            self._threads[uid] = _ThreadRunner(func, self._lock)

    def close(self):
        """Join all existing threads"""
        for uid in list(self._threads.keys()):
            self._threads.pop(uid).join()


class LifxServer:
    """LIFX Server.

    This is for managing colors and power states of lights, as well as
    pre-defined LIFX processes.
    """

    def __init__(
        self,
        server_port: int = SERVER_PORT,
        *,
        device_config_path: Union[str, pathlib.Path] = DEVICE_CONFIG,
        process_config_path: Union[str, pathlib.Path] = PROCESS_CONFIG,
        timeout: Optional[float] = SERVER_TIMEOUT,
        verbose: bool = True,
        comm_init: Optional[Callable] = None,
    ):
        """Create a LIFX server

        Args:
            server_port: (int) The TCP port to listen on.
            device_config_path: (str) Path to device config.
            process_config_path: (str) Path to process config.
            timeout: (float) Max time in ms to wait to receive a command.
            verbose: (bool) Log to INFO instead of DEBUG.
            comm_init: (function) This function (no args) creates a socket object.
        """
        self._server_port = server_port
        self._device_config_path = pathlib.Path(device_config_path)
        self._process_config_path = pathlib.Path(process_config_path)
        self._verbose = verbose

        # TODO add args for configuring the device manager on init.
        self._device_manager = device_manager.DeviceManager(
            self._device_config_path,
            verbose=verbose,
            comm_init=comm_init,
        )

        self._process_manager = process.ProcessManager(self._process_config_path)

        # TODO add option to configure threadpool size
        self._threadpool = _ThreadPool(32)

        # Setup the TCP listener
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.settimeout(timeout)
        self._socket.bind(("0.0.0.0", server_port))
        self._socket.listen(5)
        self._last_wait_timeout = False
        logging.info(f"Listening on port: 0.0.0.0:{server_port}")

        # Set the command registry
        self._commands: Dict[str, Callable] = {}
        for _, cmd in inspect.getmembers(self, predicate=_is_command):
            self._commands[cmd.label] = cmd

    def close(self) -> None:
        self._threadpool.close()
        self._socket.close()

    def _get_device_or_group(self, label: str) -> Optional[Any]:
        """Get a LIFX device object or device group object by label.

        Returns:
            The device or device group. If none with the label, return None.
        """
        if self._device_manager.has_group(label):
            return self._device_manager.get_group(label)
        elif self._device_manager.has_device(label):
            return self._device_manager.get_device(label)
        elif label == "all":
            return self._device_manager.root
        else:
            raise InvalidDeviceError(f"{label!r}")

    def recv_and_run(self) -> None:
        """Receive an incoming connection and run the command from it"""
        log_func = logging.info if self._verbose else logging.debug
        if not self._last_wait_timeout:
            log_func("Waiting for command...")
        try:
            conn, (ip, port) = self._socket.accept()
            log_func(f"Received client at address: {ip}:{port}")
            self._last_wait_timeout = False
        except socket.timeout:
            self._last_wait_timeout = True
            return

        self._threadpool.add(lambda: self._recv_and_run(conn))

    def _recv_and_run(self, conn: socket.socket) -> None:
        """Receive a command over TCP, run it, and send back the result string."""
        cmd_args = shlex.split(conn.recv(BUFFER_SIZE).decode())
        cmd_label = cmd_args.pop(0)

        cmd = self._commands.get(cmd_label)
        if not cmd:
            self._send_response(conn, ServerResponse(error=UnknownServerCommand(f"{cmd_label!r}")))
            return

        # Send help message back over TCP
        if "-h" in cmd_args or "--help" in cmd_args:
            self._send_response(conn, ServerResponse(response=cmd.parser.format_help().strip()))
            return

        # Run the command and send the result to the client
        cmd_msg = " ".join([shlex.quote(word) for word in cmd_args])
        log_func = logging.info if self._verbose else logging.debug
        log_func(f"Running command: {cmd_label} {cmd_msg}")
        try:
            kwargs = vars(cmd.parser.parse_args(cmd_args))
            response = ServerResponse(response=cmd(**kwargs))
        except Exception as error:
            logs.log_exception(error, logging.exception)
            response = ServerResponse(error=error)

        self._send_response(conn, response)

    @staticmethod
    def _send_response(conn: socket.socket, response: ServerResponse):
        """Pickle a response and send it to the client"""
        resp_bytes = pickle.dumps(response)
        size = len(resp_bytes)
        resp_bytes = f"{size}:".encode() + resp_bytes
        conn.sendall(resp_bytes)
        conn.close()

    @_command("help", "Show every server command and description.")
    def _show_help(self) -> str:
        ljust = 12
        indent = 8
        msg_lines = [
            "\n\n    LIFX Server Commands:\n",
            "".join([" " * indent, "help".ljust(ljust), self._commands["help"].description]),
        ]

        for cmd in sorted(self._commands.values(), key=lambda c: c.label):
            if cmd.label == "help":
                continue

            msg_lines.append("".join([" " * indent, cmd.label.ljust(ljust), cmd.description]))

        msg_lines.append("")
        return "\n".join(msg_lines)

    @_command("off", "Turn all lights off and stop all processes.")
    def _lights_off(self):
        self._process_manager.killall()
        self._device_manager.set_power(False)
        return "Turned off the lights."

    @_command("on", "Turn all lights on.")
    def _lights_on(self):
        self._device_manager.set_power(True)
        return "Turned on the lights."

    @_command("reload", "Reload device or process config.")
    @_add_arg("config", nargs="?", choices={"device", "process"}, help_msg="The config to reload.")
    def _reload_config(self, config: Optional[str]) -> str:
        config_loaders = {
            "device": {
                "method": self._device_manager.load_config,
                "args": (self._device_config_path,),
            },
            "process": {
                "method": self._process_manager.load_config,
                "args": (self._process_config_path,),
            },
        }

        configs_to_load = set()
        if config:
            response = f"Successfully reloaded {config} config."
            configs_to_load.add(config)
        else:
            response = "Successfully reloaded all configs."
            for key in config_loaders:
                configs_to_load.add(key)

        for conf in configs_to_load:
            logging.info(f"Reloading {conf} config.")
            loader = config_loaders[conf]
            method = loader["method"]
            args = loader.get("args", tuple())
            kwargs = loader.get("kwargs", dict())
            method(*args, **kwargs)

        return response

    @staticmethod
    def _get_device_info(device_list: List[light.LifxLight]) -> Dict[str, Dict[str, str]]:
        """Get attributes about a list of devices"""
        device_dict: Dict[str, Dict[str, str]] = {}
        for lifx_device in sorted(device_list, key=lambda l: l.label):
            device_dict[lifx_device.label] = {
                "type": type(lifx_device).__name__,
                "ip": lifx_device.ip,
            }
        return device_dict

    @staticmethod
    def _format_device_attributes(device_dict: Dict[str, Dict[str, str]]) -> str:
        """Pretty-format device attributes into a human-readable table"""
        msg_lines = []
        for label, attributes in device_dict.items():
            msg_lines.append(
                "".join(
                    [
                        " " * 8,
                        label.ljust(24),
                        attributes["type"].ljust(18),
                        attributes["ip"],
                    ]
                )
            )

        msg_lines.append("")
        return "\n".join(msg_lines)

    @_command("devices", "Show every available device.")
    @_add_arg("label", nargs="?", help_msg="Name of a device to query.")
    @_add_arg("--to-json", arg_type=bool, help_msg="Return output in json format.")
    def _show_devices(self, label: Optional[str], to_json: bool) -> str:
        if label:
            lifx_device = self._device_manager.get_device(label)
            dev_info = self._get_device_info([lifx_device])[label]
            if to_json:
                return json.dumps({label: dev_info})

            dev_type = dev_info["type"]
            dev_ip = dev_info["ip"]
            msg_lines = [
                f"\n\n    Label: {label}",
                f"    Type: {dev_type}",
                f"    IP: {dev_ip}\n",
            ]

        else:
            device_dict = self._get_device_info(self._device_manager.get_all_devices().values())
            if to_json:
                return json.dumps(device_dict)

            msg_lines = ["\n\n    LIFX Devices:\n"]
            msg_lines.append(self._format_device_attributes(device_dict))

        return "\n".join(msg_lines)

    @_command("groups", "Show every available group.")
    @_add_arg("label", nargs="?", help_msg="Name of a group to query.")
    @_add_arg("--to-json", arg_type=bool, help_msg="Return output in json format.")
    def _show_groups(self, label: Optional[str], to_json: bool) -> str:
        if label:
            lifx_group = self._device_manager.get_group(label)
            device_dict = self._get_device_info(lifx_group.get_all_devices().values())
            if to_json:
                return json.dumps(device_dict)

            msg_lines = [f"\n\n    LIFX Device Group {label}:\n"]
            msg_lines.append(self._format_device_attributes(device_dict))
        else:
            if to_json:
                return json.dumps({"groups": list(self._device_manager.get_all_groups().keys())})

            msg_lines = ["\n\n    LIFX Groups:\n"]
            for group in sorted(self._device_manager.get_all_groups().keys()):
                msg_lines.append("".join([" " * 8, group]))

            msg_lines.append("")
        return "\n".join(msg_lines)

    @_command("color", "Get or set the color of a device or group.")
    @_add_arg("label", help_msg="Device or group to set power to.")
    @_add_arg("hue", arg_type=float, nargs="?", help_msg="Hue (0-360).")
    @_add_arg("saturation", arg_type=float, nargs="?", help_msg="Saturation (0-1).")
    @_add_arg("brightness", arg_type=float, nargs="?", help_msg="Brightness (0-1).")
    @_add_arg(
        "kelvin",
        arg_type=float,
        nargs="?",
        default=color.KELVIN,
        help_msg="Kelvin color temperature.",
    )
    @_add_arg(
        "duration",
        nargs="?",
        default=0,
        arg_type=float,
        help_msg="Transition time in seconds.",
    )
    @_add_arg("--machine", arg_type=bool, help_msg="Return machine-readable string output.")
    def _set_color(
        self,
        *,
        label: str,
        hue: Optional[float],
        saturation: Optional[float],
        brightness: Optional[float],
        kelvin: int,
        duration: float,
        machine: bool,
    ) -> str:
        lifx_device = self._get_device_or_group(label)

        assert lifx_device is not None
        if any([hue is None, saturation is None, brightness is None]):
            if isinstance(lifx_device, device_manager.DeviceGroup):
                raise UnknownServerCommand("Cannot get color state of a device group.")
            hsbk = lifx_device.get_color()
        else:
            hsbk = color.Hsbk.from_tuple((hue, saturation, brightness, kelvin))
            lifx_device.set_color(hsbk, duration=duration)

        msg = ""
        if machine:
            msg = ""
        else:
            hsbk_str = "\n".join(
                [
                    f"hue: {hsbk.hue}",
                    f"saturation: {hsbk.saturation}",
                    f"brightness: {hsbk.brightness}",
                    f"kelvin: {hsbk.kelvin}",
                ]
            )
            if lifx_device == self._device_manager.root:
                label = "Global"
            msg = f"{label} color state:\n{hsbk_str}"
        return msg

    @_command("cmap", "Set a device or group to a matplotlib colormap.")
    @_add_arg("label", arg_type=str, nargs="?", help_msg="Device or group to set power to.")
    @_add_arg("colormap", arg_type=str, nargs="?", help_msg="Name of any matplotlib colormap.")
    @_add_arg(
        "duration",
        nargs="?",
        default=0,
        arg_type=float,
        help_msg="Transition time in seconds.",
    )
    @_add_arg(
        "division",
        nargs="?",
        default=2,
        arg_type=int,
        help_msg="Number of divisions per square for tiles.",
    )
    def _set_colormap(
        self,
        *,
        label: str,
        colormap: Optional[str],
        duration: float,
        division: int,
    ) -> str:

        # Print colormaps and return
        if not colormap:
            msg_lines = ["\n\n    Matplotlib Colormaps:\n"]
            for cmap_name in color.get_all_colormaps():
                if cmap_name.endswith("_r"):
                    continue
                msg_lines.append("".join([" " * 8, cmap_name]))

            msg_lines.append("")
            return "\n".join(msg_lines)

        # Set the colormap
        lifx_device = self._get_device_or_group(label)
        assert lifx_device is not None
        if hasattr(lifx_device, "set_colormap"):
            kwargs = {"cmap": colormap, "duration": duration}
            if isinstance(lifx_device, (tile.LifxTile, device_manager.DeviceGroup)):
                kwargs["division"] = division
            lifx_device.set_colormap(**kwargs)
            if lifx_device == self._device_manager.root:
                label = "Global"
            return f"{label} colormap: {colormap}"
        else:
            raise InvalidDeviceError(f"Device {label} does not support colormaps.")

    @_command("power", "Get or set the power of a device or group.")
    @_add_arg("label", help_msg="Device or group to set power to.")
    @_add_arg("state", nargs="?", choices={"on", "off"}, help_msg="Set the power state.")
    @_add_arg(
        "duration",
        nargs="?",
        default=0,
        arg_type=float,
        help_msg="Transition time in seconds.",
    )
    @_add_arg("--machine", arg_type=bool, help_msg="Return machine-readable string output.")
    def _set_power(
        self,
        *,
        label: str,
        state: Optional[str],
        duration: float,
        machine: bool,
    ) -> str:
        lifx_device = self._get_device_or_group(label)
        assert lifx_device is not None
        if not state:
            if isinstance(lifx_device, device_manager.DeviceGroup):
                raise UnknownServerCommand("Cannot get power state of a device group.")
            state = "on" if lifx_device.get_power() else "off"
        else:
            lifx_device.set_power(state == "on", duration=duration)

        if lifx_device == self._device_manager.root:
            label = "Global"
        if machine:
            return "0" if state == "off" else "1"
        else:
            return f"{label} power state: {state}"

    def _check_running_processes(
        self, *, to_json: bool = False, kill_oneshot: bool = False
    ) -> Optional[str]:
        """Check running processes for errors and construct a message"""
        failures = self._process_manager.check_failures(kill_oneshot=kill_oneshot)
        if to_json:
            return json.dumps(
                {
                    label: {
                        "returncode": failure.returncode,
                        "stdout": failure.stdout,
                        "stderr": failure.stderr,
                    }
                    for label, failure in failures.items()
                }
            )

        tab = 4 * " "
        tab2 = 2 * tab
        msg_lines = []
        for label, failure in sorted(failures.items(), key=lambda tt: tt[0]):
            msg_lines.append(f"\n{label} returncode: {failure.returncode}")
            if failure.stdout:
                msg_lines.append(f"{tab}stdout:")
                for line in failure.stdout.splitlines():
                    msg_lines.append(f"{tab2}{line}")
                if failure.stderr:
                    msg_lines.append("")
            if failure.stderr:
                msg_lines.append(f"{tab}stderr:")
                for line in failure.stderr.splitlines():
                    msg_lines.append(f"{tab2}{line}")

        if msg_lines:
            msg_lines.insert(0, "Processes with errors:")
            return "\n".join(msg_lines).strip()

    @_command("check", "Check running processes for failures.")
    @_add_arg("--to-json", arg_type=bool, help_msg="Return output in json format.")
    @_add_arg(
        "--kill-oneshot",
        arg_type=bool,
        help_msg="Kill any non-ongoing processes that may be lingering.",
    )
    def _print_check(self, to_json: bool, kill_oneshot: bool) -> str:
        msg = self._check_running_processes(to_json=to_json, kill_oneshot=kill_oneshot)
        if msg:
            return msg
        else:
            return "No processes with errors."

    @_command("list", "List available and running processes.")
    @_add_arg("--to-json", arg_type=bool, help_msg="Return output in json format.")
    def _list_processes(self, to_json: bool) -> str:
        if not to_json:
            check_msg = self._check_running_processes()
            if check_msg:
                return check_msg

        available, running = self._process_manager.get_available_and_running()
        if to_json:
            return json.dumps(
                {
                    "available": [p.label for p in available],
                    "running": [p.label for p in running],
                }
            )

        if not available and not running:
            return "No available or running processes."

        ljust = 24
        tab = " " * 4
        tab2 = 2 * tab
        msg_lines = ["LIFX Processes\n"]
        if available:
            msg_lines.append(f"{tab}Available processes:")
            for proc in sorted(available, key=lambda p: p.label):
                msg_lines.append("".join([tab2, proc.label.ljust(ljust), proc.filename.name]))

        if running:
            if available:
                msg_lines.append("")
            msg_lines.append(f"{tab}Running processes:")
            for proc in sorted(running, key=lambda p: p.label):
                msg_lines.append("".join([tab2, proc.label.ljust(ljust), proc.filename.name]))

        msg_lines.append("")
        return "\n".join(msg_lines)

    @_command("killall", "Kill all running processes.")
    def _killall_processes(self) -> str:
        self._process_manager.killall()
        return "Killed all running processes."

    @_command("start", "Start a LIFX process.")
    @_add_arg("label", help_msg="Label of the process to start.")
    @_add_arg("argv", nargs=argparse.REMAINDER, help_msg="Extra args to pass into the process.")
    def _start_process(self, label: str, argv: List[str]) -> str:
        self._process_manager.start(label, argv)
        return f"Started process: {label}"

    @_command("restart", "Restart a LIFX process.")
    @_add_arg("label", help_msg="Label of the process to restart.")
    @_add_arg("argv", nargs=argparse.REMAINDER, help_msg="Extra args to pass into the process.")
    def _restart_process(self, label: str, argv: List[str]) -> str:
        self._process_manager.restart(label, argv)
        return f"Restarted process: {label}"

    @_command("stop", "Stop a LIFX process.")
    @_add_arg("label", help_msg="Label of the process to stop.")
    def _stop_process(self, label: str) -> str:
        self._process_manager.stop(label)
        return f"Stopped process: {label}"

    @_command("status", "Check if a process is running")
    @_add_arg("label", help_msg="Name of a process to query.")
    @_add_arg("--machine", arg_type=bool, help_msg="Return machine-readable string output.")
    def _check_process_status(self, label: str, machine: bool) -> str:
        available_msg = {True: "0", False: f"Process {label!r} is not running."}
        running_msg = {True: "1", False: f"Process {label!r} is running."}

        if self._process_manager.get_process(label).running:
            return running_msg[machine]
        else:
            return available_msg[machine]


@click.command()
@click.option(
    "-p",
    "--port",
    default=SERVER_PORT,
    type=int,
    show_default=True,
    help="TCP Port of the LIFX server.",
)
@click.option(
    "--device-config",
    default=DEVICE_CONFIG,
    type=str,
    show_default=True,
    help="LIFX device config file.",
)
@click.option(
    "--process-config",
    default=PROCESS_CONFIG,
    type=str,
    show_default=True,
    help="LIFX process config file.",
)
@click.option(
    "-q",
    "--quiet",
    is_flag=True,
    help="Suppress INFO logs to DEBUG.",
)
@click.option(
    "-t",
    "--timeout",
    default=SERVER_TIMEOUT,
    type=float,
    show_default=True,
    help="Server timeout in seconds. <=0 disables the timeout",
)
def main(port: int, device_config: str, process_config, quiet: bool, timeout: float):
    logs.setup()

    lifx = LifxServer(
        port,
        timeout=timeout if timeout > 0 else None,
        device_config_path=device_config,
        process_config_path=process_config,
        verbose=not quiet,
    )
    while True:
        lifx.recv_and_run()
