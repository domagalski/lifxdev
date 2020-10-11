#!/usr/bin/env python3

import logging
import pathlib
import re
import socket
import subprocess as spr
from typing import Dict, Union

import click
import yaml
import zmq

from lifxdev.messages import packet
from lifxdev.server import client
from lifxdev.server import server
from lifxdev.server import logs


DEFAULT_LIFX_HOST = "localhost"
DEFAULT_LIFX_PORT = server.SERVER_PORT
DEFAULT_LIFX_TIMEOUT = 30000
DEFAULT_DHCP_TRIGGER_PORT = 16385
DEFAULT_CONFIG_PATH = pathlib.Path.home() / ".lifx" / "dhcp-trigger.yaml"
DHCP_RE_PATTERN = " ".join([r"\S+", ":".join([r"\S\S"] * 6), ".".join([r"\d+"] * 4)])


class DhcpTrigger:
    def __init__(
        self,
        config_path: Union[str, pathlib.Path] = DEFAULT_CONFIG_PATH,
        listen_port: int = DEFAULT_DHCP_TRIGGER_PORT,
        lifx_server_ip: str = DEFAULT_LIFX_HOST,
        lifx_server_port: int = DEFAULT_LIFX_PORT,
        lifx_server_timeout: int = DEFAULT_LIFX_TIMEOUT,
    ):
        """Create a DHCP trigger object.

        Config example:

        <cmd_label>:
          # command is a required keyword
          command: <lifx_server_command>
          macs:
            - <mac_addr_1>
            - <mac_addr_2>
            - ...

        Args:
            config_path: (str) Path to the config file. This is required to exist.
            listen_port: (int) The TCP port to listen on for new DHCP connection info.
            lifx_server_ip: (str) The IP address of the LIFX server.
            lifx_server_port: (int) The port of the LIFX server.
            lifx_server_timeout: (int) The timeout in milliseconds for LIFX server commands.
        """
        config_path = pathlib.Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(config_path)

        with config_path.open() as f:
            config = yaml.safe_load(f)

        # Dictionary containing all MAC addresses and their command-type
        self._all_macs: Dict[str, str] = {}

        # Dictionary containing commands
        self._commands: Dict[str, str] = {}

        # Load the configuration
        for cmd_label, cmd_conf in config.items():
            self._commands[cmd_label] = cmd_conf["command"]
            for mac in cmd_conf.get("macs", []):
                self._all_macs[mac.lower()] = cmd_label

        # set up the socket listener
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(("", listen_port))
        self._socket.listen(1)

        # Set up the LIFX client
        self._lifx = client.LifxClient(lifx_server_ip, lifx_server_port, lifx_server_timeout)

    def close(self) -> None:
        """Close sockets"""
        self._socket.close()
        self._lifx.close()

    @staticmethod
    def _ping(ip: str, *, timeout: int) -> bool:
        """ping an address and return true if reachable.

        Args:
            ip: (str) IP address to ping
            timeout: (int) Ping timeout in seconds.
        """
        ping_cmd = ["ping", "-c", "1", "-w", str(timeout), ip]
        return not spr.call(ping_cmd, stdout=spr.DEVNULL, stderr=spr.DEVNULL)

    def wait_for_connection(self) -> None:
        """Wait for IP info from dnsmasq and process it

        Return quietly if the IP info is invalid.
        """
        # Get DHCP info over TCP
        conn, _ = self._socket.accept()
        ip_info = bytes.decode(conn.recv(1024)).strip()
        conn.close()

        # Verify the pattern
        if not re.match(DHCP_RE_PATTERN, ip_info):
            logging.error(f"Invalid message: {ip_info}")
            return

        # Parse the DHCP info
        state, mac, ip = ip_info.split()
        state = state.lower()
        mac = mac.lower()

        # Drop invalid MAC/IP addresses
        if not (packet.is_str_mac(mac) and packet.is_str_ipaddr(ip)):
            logging.error(f"Invalid message: {ip_info}")
            return

        # Don't care about deletes. Only care about new connections.
        if state not in ["add", "old"]:
            logging.info(f"Ignoring message: {ip_info}")
            return

        # Return if the mac address is not in the config.
        if mac not in self._all_macs:
            logging.info(f"Ignoring message: {ip_info}")
            return

        # Return if the IP can't be pinged.
        if not self._ping(ip, timeout=5):
            logging.error(f"Cannot ping IP: {ip}")
            return

        # Run the commands associated with the mac address
        logging.info(f"Detected MAC address {mac} at IP: {ip}")
        cmd_label = self._all_macs[mac]
        cmd = self._commands[cmd_label]
        response = self._lifx.send_recv(cmd)
        if response.response:
            logging.info(response.response)
        elif response.error:
            logging.error(f"Failed to run LIFX server command: {cmd}")
            logs.log_exception(response.error, logging.error)


@click.command()
@click.option(
    "-c",
    "--config-path",
    default=DEFAULT_CONFIG_PATH,
    show_default=True,
    help="Path to config file.",
)
@click.option(
    "-p",
    "--port",
    type=int,
    default=DEFAULT_DHCP_TRIGGER_PORT,
    show_default=True,
    help="TCP port to listen for DHCP connections.",
)
@click.option(
    "--lifx-ip",
    default=DEFAULT_LIFX_HOST,
    show_default=True,
    help="IP address of the LIFX server.",
)
@click.option(
    "--lifx-port",
    type=int,
    default=DEFAULT_LIFX_PORT,
    show_default=True,
    help="Port of the LIFX server.",
)
@click.option(
    "--lifx-timeout",
    type=int,
    default=DEFAULT_LIFX_TIMEOUT,
    show_default=True,
    help="Timeout in milliseconds for LIFX server communications. -1 means no timeout.",
)
def main(
    config_path: Union[str, pathlib.Path],
    port: int,
    lifx_ip: str,
    lifx_port: int,
    lifx_timeout: int,
):
    logs.setup()
    dhcp_trigger = DhcpTrigger(config_path, port, lifx_ip, lifx_port, lifx_timeout)
    logging.info(f"Listening for DHCP connections on port: {port}")
    logging.info(f"LIFX client: {lifx_ip}:{lifx_port}")
    while True:
        try:
            dhcp_trigger.wait_for_connection()
        except zmq.ZMQError:
            logging.error("Cannot communicate with LIFX server. Retrying...")
            continue
        finally:
            dhcp_trigger.close()
            break


if __name__ == "__main__":
    main()
