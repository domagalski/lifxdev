#!/usr/bin/env python3

import argparse
import inspect
import logging
import pathlib
import shlex
import socket
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Set, Type, Union

import click
import zmq

from lifxdev.devices import device_manager
from lifxdev.server import logs

SERVER_PORT = 16384
DOT_LIFX = pathlib.Path.home() / ".lifx"
DEVICE_CONFIG = pathlib.Path.home() / ".lifx" / "devices.yaml"
PROCESS_CONFIG = pathlib.Path.home() / ".lifx" / "processes.yaml"


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
        if not hasattr(function, "arg_list"):
            function.arg_list = []
        function.parser = _CommandParser(prog=label, description=description)
        for flags, kwargs in reversed(function.arg_list):
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
) -> Callable:
    """Register argument parsing options to a server command

    Args:
        flags: Argument name. Must be the same as the function call.
        help_msg: Help message to display for an argument.
        arg_type: The data type to convert strings to.
        default: The default value of the argument.
        required: Whether or not the argument is required.
        choices: Iterable of valid choices for the argument.
    """

    def _add_arg_to_method(function: Callable):
        if not hasattr(function, "arg_list"):
            function.arg_list = []

        kwargs = {"help": help_msg}
        if arg_type == bool:
            kwargs["action"] = "store_true"
        else:
            kwargs["default"] = default
            kwargs["type"] = arg_type
        if flags[0][0] == "-":
            kwargs["required"] = required
        if choices:
            kwargs["choices"] = choices

        function.arg_list.append((flags, kwargs))
        return function

    return _add_arg_to_method


class ServerResponse(NamedTuple):
    response: Optional[str] = None
    error: Optional[Exception] = None


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
        verbose: bool = True,
        comm: Optional[socket.socket] = None,
    ):
        """Create a LIFX server

        Args:
            server_port: (int) The TCP port to listen on.
            device_config_path: (str) Path to device config.
            process_config_path: (str) Path to process config.
            verbose: (bool) Log to INFO instead of DEBUG.
            comm: (socket) Override the default UDB socket object.
        """
        self._device_config_path = pathlib.Path(device_config_path)
        self._process_config_path = pathlib.Path(process_config_path)

        # TODO add args for configuring the device manager on init.
        self._device_manager = device_manager.DeviceManager(
            self._device_config_path,
            verbose=verbose,
            comm=comm,
        )

        # Setup ZMQ
        self._zmq_socket = zmq.Context().socket(zmq.REP)
        self._zmq_socket.bind(f"tcp://*:{server_port}")

        # Set the command registry
        self._commands: Dict[str, Callable] = {}
        for _, cmd in inspect.getmembers(self, predicate=_is_command):
            self._commands[cmd.label] = cmd

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
        """Receive a command over ZMQ, run it, and send back the result string."""
        logging.info("Waiting for command...")
        cmd_args = shlex.split(self._zmq_socket.recv_string())
        cmd_label = cmd_args.pop(0)

        cmd = self._commands.get(cmd_label)
        if not cmd:
            response = ServerResponse(error=UnknownServerCommand(f"{cmd_label!r}"))
            self._zmq_socket.send_pyobj(response)
            return

        # Send help message back over ZMQ
        if "-h" in cmd_args or "--help" in cmd_args:
            response = ServerResponse(response=cmd.parser.format_help().strip())
            self._zmq_socket.send_pyobj(response)
            return

        # Run the command and send the result to the client
        cmd_msg = " ".join([shlex.quote(word) for word in cmd_args])
        logging.info(f"Running command: {cmd_label} {cmd_msg}")
        try:
            kwargs = vars(cmd.parser.parse_args(cmd_args))
            response = ServerResponse(response=cmd(**kwargs))
        except Exception as error:
            logs.log_exception(error, logging.exception)
            response = ServerResponse(error=error)
        self._zmq_socket.send_pyobj(response)
        logging.info("Response sent to client.")

    @_command("power", "Get or set the power of a device or group.")
    @_add_arg("label", help_msg="Device or group to set power to.")
    @_add_arg("state", choices={"on", "off", "state"}, help_msg="Get or set the power state.")
    @_add_arg("--duration", default=0, arg_type=float, help_msg="Transition time in seconds.")
    @_add_arg("--machine", arg_type=bool, help_msg="Return machine-readable string output.")
    def _set_power(
        self, *, label: str, state: Optional[str], duration: float, machine: bool
    ) -> str:
        lifx_device = self._get_device_or_group(label)
        if state == "state":
            if isinstance(lifx_device, device_manager.DeviceGroup):
                raise UnknownServerCommand("Cannot get power state of a device group.")
            state = "on" if lifx_device.get_power() else "off"
        else:
            lifx_device.set_power(state == "on", duration)

        if machine:
            return "0" if state == "off" else "1"
        elif lifx_device == self._device_manager._root_device_group:
            return f"Powering all lights {state}."
        else:
            return f"{label} power state: {state}"


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
def main(port: int, device_config: str, process_config, quiet: bool):
    logs.setup()

    lifx = LifxServer(
        port,
        device_config_path=device_config,
        process_config_path=process_config,
        verbose=not quiet,
    )
    while True:
        lifx.recv_and_run()
