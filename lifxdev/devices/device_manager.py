#!/usr/bin/env python3

import pathlib
import socket
from typing import Any, Dict, List, Optional

import yaml

from lifxdev.devices import device
from lifxdev.devices import light
from lifxdev.devices import multizone
from lifxdev.devices import tile
from lifxdev.messages import packet
from lifxdev.messages import device_messages


class DeviceManager(device.LifxDevice):
    """Device manager

    Class for device discovery and loading configs.
    """

    def __init__(
        self,
        buffer_size: int = packet.BUFFER_SIZE,
        timeout: Optional[float] = None,
        nonblock_delay: float = packet.NONBOCK_DELAY,
        comm: Optional[socket.socket] = None,
    ):
        """Create a LIFX device manager.

        Args:
            buffer_size: (int) Buffer size for receiving UDP responses.
            timeout: (float) UDP response timeout.
            nonblock_delay: (float) Delay time to wait for messages when nonblocking.
            verbose: (bool) Use logging.info instead of logging.debug.
            comm: (socket) Optionally override the socket used for the device class.
        """
        super().__init__(
            ip="255.255.255.255",
            broadcast=True,
            buffer_size=buffer_size,
            timeout=timeout,
            nonblock_delay=nonblock_delay,
            verbose=True,
            comm=comm,
        )

        # Load product identification
        products = pathlib.Path(__file__).parent / "products.yaml"
        with products.open() as f:
            product_list = yaml.safe_load(f).pop().get("products", [])

        # For easily recovering product info via get_product_class
        self._products: Dict[str, Any] = {}
        for product in product_list:
            self._products[product["pid"]] = product

    def get_devices(self) -> List[packet.LifxResponse]:
        """Get device info from one or more devices.

        Args:
            ip: (str) Override the IP address.
            port: (int) Override the UDP port.
            mac_addr: (str) Override the MAC address.
            comm: (socket) Override the UDP socket.

        Returns:
            A list of StateService responses.
        """
        return self.send_recv(device_messages.GetService(), res_required=True)

    def get_label(
        self,
        ip: str,
        *,
        port: int = packet.LIFX_PORT,
        mac_addr: Optional[int] = None,
        comm: Optional[socket.socket] = None,
    ) -> str:
        """Get the label of a device

        Args:
            ip: (str) Override the IP address.
            port: (int) Override the UDP port.
            mac_addr: (str) Override the MAC address.
            comm: (socket) Override the UDP socket.
        """
        return (
            self.send_recv(
                device_messages.GetLabel(),
                res_required=True,
                ip=ip,
                port=port,
                mac_addr=mac_addr,
                comm=comm,
            )
            .pop()
            .payload["label"]
        )

    def get_product_info(
        self,
        ip: str,
        *,
        port: int = packet.LIFX_PORT,
        mac_addr: Optional[int] = None,
        comm: Optional[socket.socket] = None,
    ) -> Dict[str, Any]:
        """Get the Python class needed to control a LIFX product.

        Args:
            ip: (str) Override the IP address.
            port: (int) Override the UDP port.
            mac_addr: (str) Override the MAC address.
            comm: (socket) Override the UDP socket.
        """
        product_id = (
            self.send_recv(
                device_messages.GetVersion(),
                res_required=True,
                ip=ip,
                port=port,
                mac_addr=mac_addr,
                comm=comm,
            )
            .pop()
            .payload["product"]
        )

        # Get the class definition from the product info
        product = self._products[product_id]
        features = product["features"]
        if features["multizone"]:
            klass = multizone.LifxMultiZone
        elif features["matrix"]:
            klass = tile.LifxTile
        elif features["infrared"]:
            klass = light.LifxInfraredLight
        else:
            klass = light.LifxLight

        product["class"] = klass
        return product
