#!/usr/bin/env python3

from __future__ import annotations

import logging
import pickle
import shlex
import socket
import sys

import click

from lifxdev.server import server
from lifxdev.server import logs


BUFFER_SIZE = 1024


class LifxClient:
    """LIFX Client.

    This is for managing colors and power states of lights, as well as
    pre-defined LIFX processes.
    """

    def __init__(
        self,
        ip: str = "127.0.0.1",
        port: int = server.SERVER_PORT,
        timeout: float | None = None,
    ):
        """Create a LIFX client

        Args:
            ip: (str) The IP address to connect to.
            port: (int) The TCP port to connect to.
            timeout: (float) Timeout in milliseconds. None means no timeout.
        """
        self._addr = (ip, port)
        self._timeout = timeout
        self._socket = None

    def connect(self) -> None:
        if self._socket:
            raise FileExistsError("Socket already in use.")

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(self._timeout)
        self._socket.connect(self._addr)

    def close(self) -> None:
        """Close the TCP socket"""
        if not self._socket:
            raise BrokenPipeError("Socket already closed.")

        self._socket.close()
        self._socket = None

    def __call__(self, cmd_and_args: str) -> str:
        """Send a command to the server and log/raise a response message/error.

        Returns:
            The text of the response.

        Raises:
            If the response contains an error, raise it.
        """
        response = self.send_recv(cmd_and_args)
        if response.error:
            raise response.error
        else:
            assert response.response is not None
            return response.response

    def send_recv(self, cmd_and_args: str) -> server.ServerResponse:
        """Send a command to the server and receive a response message"""
        self.connect()
        assert self._socket is not None
        self._socket.send(cmd_and_args.encode())
        recv_bytes = self._socket.recv(BUFFER_SIZE)
        if not recv_bytes:
            raise EOFError("EOF received from server.")

        size, packet = recv_bytes.split(b":", maxsplit=1)
        size = int(size)
        while len(packet) < size:
            packet += self._socket.recv(BUFFER_SIZE)
        self.close()
        return pickle.loads(packet)


@click.command()
@click.option(
    "-i",
    "--ip",
    default="localhost",
    type=str,
    show_default=True,
    help="IP of the LIFX server.",
)
@click.option(
    "-p",
    "--port",
    default=server.SERVER_PORT,
    type=int,
    show_default=True,
    help="TCP Port of the LIFX server.",
)
@click.option("-t", "--timeout", type=float, help="Timeout in seconds.")
@click.argument("cmd", nargs=-1)
def main(ip: str, port: int, timeout: float | None, cmd: tuple[str, ...]):
    """Control LIFX devices and processes."""

    logs.setup()
    if not cmd:
        logging.error("Missing command!")
        sys.exit(1)

    exit_code = 1
    cmd_str = " ".join([shlex.quote(word) for word in cmd])
    lifx = LifxClient(ip, port, timeout=timeout)
    try:
        logging.info(lifx(cmd_str))
        exit_code = 0
    except (socket.timeout, ConnectionRefusedError):
        logging.critical("Cannot communicate with LIFX server.")
    except Exception as e:
        logs.log_exception(e, logging.error)
    sys.exit(exit_code)
