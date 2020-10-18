#!/usr/bin/env python3

import logging
import shlex
import sys
from typing import Tuple

import click
import zmq

from lifxdev.server import server
from lifxdev.server import logs


class LifxClient:
    """LIFX Client.

    This is for managing colors and power states of lights, as well as
    pre-defined LIFX processes.
    """

    def __init__(self, ip: str = "localhost", port: int = server.SERVER_PORT, timeout: int = -1):
        """Create a LIFX client

        Args:
            ip: (str) The IP address to connect to.
            port: (int) The TCP port to connect to.
            timeout: (int) ZMQ timeout in milliseconds. -1 means no timeout.
        """
        self._zmq_addr = f"tcp://{ip}:{port}"
        self._zmq_socket = None
        self._timeout = timeout
        self.connect()

    def connect(self) -> None:
        """Connect to the ZMQ socket"""
        if self._zmq_socket:
            raise FileExistsError("ZMQ socket in use.")

        self._zmq_socket = zmq.Context().socket(zmq.REQ)
        self._zmq_socket.setsockopt(zmq.RCVTIMEO, self._timeout)
        self._zmq_socket.setsockopt(zmq.SNDTIMEO, self._timeout)
        self._zmq_socket.connect(self._zmq_addr)

    def close(self) -> None:
        """Close the ZMQ socket"""
        if not self._zmq_socket:
            raise BrokenPipeError("ZMQ socket already closed.")

        self._zmq_socket.close(linger=0)
        self._zmq_socket = None

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
            return response.response

    def send_recv(self, cmd_and_args: str) -> server.ServerResponse:
        """Send a command to the server and receive a response message"""
        self._zmq_socket.send_string(cmd_and_args)
        return self._zmq_socket.recv_pyobj()


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
@click.option(
    "-t",
    "--timeout",
    default=-1,
    type=float,
    show_default=True,
    help="ZMQ Timeout in seconds. -1 disables the timeout",
)
@click.argument("cmd", nargs=-1)
def main(ip: str, port: int, timeout: float, cmd: Tuple[str, ...]):
    """Control LIFX devices and processes."""

    logs.setup()
    if not cmd:
        logging.error("Missing command!")
        sys.exit(1)

    exit_code = 1
    timeout = 5 if (len(cmd) == 1 and timeout == -1) else timeout
    cmd = " ".join([shlex.quote(word) for word in cmd])
    lifx = LifxClient(ip, port, timeout=-1 if timeout < 0 else int(timeout * 1000))
    try:
        logging.info(lifx(cmd))
        exit_code = 0
    except zmq.ZMQError:
        logging.critical("Cannot communicate with LIFX server.")
    except Exception as e:
        logs.log_exception(e, logging.error)
    finally:
        lifx.close()
    sys.exit(exit_code)
