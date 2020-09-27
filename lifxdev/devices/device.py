#!/usr/bin/env python3

import socket
from typing import List, Optional

from lifxdev.messages import packet
from lifxdev.messages import device_messages


class LifxDevice:
    """LIFX device control"""

    def __init__(self, comm: packet.UdpSender, verbose: bool = True):
        self._comm = packet.PacketComm(comm, verbose)
        self._verbose = verbose

    @classmethod
    def init_from_ip_addr(
        cls,
        ip: str,
        mac_addr: Optional[str] = None,
        port: int = packet.LIFX_PORT,
        buffer_size: int = packet.BUFFER_SIZE,
        timeout: Optional[float] = None,
        nonblock_delay: float = packet.NONBOCK_DELAY,
        broadcast: bool = False,
        verbose: bool = False,
        comm: Optional[socket.socket] = None,
    ) -> "LifxDevice":
        """Create a LIFX device from an IP address

        Args:
            ip: (str) IP addess of the device.
            mac_addr: (str) Mac address of the device.
            port: (int) UDP port of the device.
            buffer_size: (int) Buffer size for receiving UDP responses.
            timeout: (float) UDP response timeout.
            broadcast: (bool) Whether the IP address is a broadcast address.
            verbose: (bool) Use logging.info instead of logging.debug.
            comm: (socket) Optionally override the socket used for the device class.
        """
        comm = comm or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        comm.settimeout(timeout)
        if broadcast:
            comm.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            comm.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp_sender = packet.UdpSender(
            mac_addr=mac_addr,
            ip=ip,
            comm=comm,
            buffer_size=buffer_size,
            nonblock_delay=nonblock_delay,
        )
        return cls(udp_sender, verbose)

    def send_msg(
        self,
        payload: packet.LifxMessage,
        *,
        ack_required,
        bool=True,
        verbose: bool = False,
    ) -> Optional[packet.LifxResponse]:
        """Send a message to a device.

        This can be used to send any LIFX message to the device. Functions
        that send messages to the device will all wrap this function. This
        function can be used when a wrapper for a message is not available.

        Args:
            payload: (packet.LifxMessage) LIFX message to send to a device.
            ack_required: (bool) Require an acknowledgement from the device.
            verbose: (bool) Log messages as info instead of debug.
        """
        response = self.send_recv(payload, ack_required=ack_required, verbose=verbose)
        if response:
            return response[0]

    def send_recv(
        self,
        payload: packet.LifxMessage,
        *,
        res_required: bool = False,
        ack_required: bool = False,
        verbose: bool = False,
    ) -> Optional[List[packet.LifxResponse]]:
        """Send a message to a device or broadcast address.

        This can be used to send any LIFX message to the device. Functions
        that send messages to the device will all wrap this function. This
        function can be used when a wrapper for a message is not available.

        Args:
            payload: (packet.LifxMessage) LIFX message to send to a device.
            res_required: (bool) Require a response from the light.
            ack_required: (bool) Require an acknowledgement from the device.
            verbose: (bool) Log messages as info instead of debug.
        """
        if res_required and ack_required:
            raise ValueError("Cannot set both res_required and ack_required to True.")
        return self._comm.send_recv(
            payload=payload,
            res_required=res_required,
            ack_required=ack_required,
            verbose=verbose or self._verbose,
        )

    def get_device_info(self) -> List[packet.LifxResponse]:
        """Get device info from one or more devices. Returns a list."""
        return self.send_recv(device_messages.GetService(), res_required=True)

    def get_power(self) -> bool:
        """Return True if the light is powered on."""
        response = self.send_recv(device_messages.GetPower(), res_required=True)
        return response[0].payload["level"]

    def set_power(self, state: bool, *, ack_required=True) -> Optional[packet.LifxResponse]:
        """Set power state on the device"""
        power = device_messages.SetPower(level=state)
        return self.send_recv(power, ack_required=ack_required)
