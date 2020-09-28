#!/usr/bin/env python3

import logging
import pathlib
import socket
from typing import Any, Dict, List, NamedTuple, Optional

import yaml

from lifxdev.devices import device
from lifxdev.devices import light
from lifxdev.devices import multizone
from lifxdev.devices import tile
from lifxdev.messages import packet
from lifxdev.messages import device_messages


class ProductInfo(NamedTuple):
    ip: str
    port: int
    label: str
    product_name: str
    device: light.LifxLight


class DeviceManager(device.LifxDevice):
    """Device manager

    Class for device discovery and loading configs.
    """

    def __init__(
        self,
        *,
        buffer_size: int = packet.BUFFER_SIZE,
        timeout: Optional[float] = packet.TIMEOUT,
        nonblock_delay: float = packet.NONBOCK_DELAY,
        verbose: bool = False,
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
            verbose=verbose,
            comm=comm,
        )

        self._timeout = timeout

        # Load product identification
        products = pathlib.Path(__file__).parent / "products.yaml"
        with products.open() as f:
            product_list = yaml.safe_load(f).pop().get("products", [])

        # For easily recovering product info via get_product_class
        self._products: Dict[str, Any] = {}
        for product in product_list:
            self._products[product["pid"]] = product

    def discover(
        self,
        num_retries: int = 10,
        device_comm: Optional[socket.socket] = None,
    ) -> List[ProductInfo]:
        """Discover devices on the network

        Args:
            num_retries: (int) Number of GetService calls made.
            timeout:
        """

        logging.info("Scanning for LIFX devices.")
        state_service_dict: Dict[str, packet.LifxResponse] = {}
        # Disabling the timeout speeds up discovery
        self.set_timeout(None)
        for ii in range(num_retries):
            if ii + 1 == num_retries:
                # Use a timeout on the last get_devices to ensure no lingering packets
                self.set_timeout(self._timeout)
            search_responses = self.get_devices()
            for response in search_responses:
                ip = response.addr[0]
                state_service_dict[ip] = response

        self.set_timeout(None)
        logging.info("Getting device info for discovered devices.")
        # Device manager has different socket options than unicast devices
        device_comm = device_comm or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        device_comm.settimeout(self._timeout)
        device_list: List[ProductInfo] = []
        for ip, state_service in state_service_dict.items():
            port = state_service.payload["port"]
            try:
                label = self.get_label(ip, port=port, comm=device_comm)
                product_dict = self.get_product_info(ip, port=port, comm=device_comm)
            except packet.NoResponsesError as e:
                logging.error(e)
                continue

            product_name = product_dict["name"]
            device_klass = product_dict["class"]

            product_info = ProductInfo(
                ip=ip,
                port=port,
                label=label,
                product_name=product_name,
                device=device_klass(
                    ip,
                    port=port,
                    comm=device_comm,
                    timeout=self._timeout,
                    verbose=self._verbose,
                ),
            )
            device_list.append(product_info)

        return device_list

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
        return self.send_recv(device_messages.GetService(), res_required=True, retry_recv=True)

    def get_label(
        self,
        ip: str,
        *,
        port: int = packet.LIFX_PORT,
        mac_addr: Optional[str] = None,
        comm: Optional[socket.socket] = None,
        verbose: bool = False,
    ) -> str:
        """Get the label of a device

        Args:
            ip: (str) Override the IP address.
            port: (int) Override the UDP port.
            mac_addr: (str) Override the MAC address.
            comm: (socket) Override the UDP socket.
            verbose: (bool) Use logging.info instead of logging.debug.
        """
        return (
            self.send_recv(
                device_messages.GetLabel(),
                res_required=True,
                ip=ip,
                port=port,
                mac_addr=mac_addr,
                comm=comm,
                verbose=verbose,
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
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """Get the Python class needed to control a LIFX product.

        Args:
            ip: (str) Override the IP address.
            port: (int) Override the UDP port.
            mac_addr: (str) Override the MAC address.
            comm: (socket) Override the UDP socket.
            verbose: (bool) Use logging.info instead of logging.debug.
        """
        product_id = (
            self.send_recv(
                device_messages.GetVersion(),
                res_required=True,
                ip=ip,
                port=port,
                mac_addr=mac_addr,
                comm=comm,
                verbose=verbose,
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


if __name__ == "__main__":
    import coloredlogs

    coloredlogs.install(level=logging.INFO, fmt="%(asctime)s %(levelname)s %(message)s")

    device_manager = DeviceManager()
    devices = device_manager.discover()
    for device_info in sorted(devices, key=lambda d: d.ip):
        product = device_info.product_name
        ip = device_info.ip
        label = device_info.label
        logging.info(f"{ip}:\tDiscovered {product}: {label}")
    logging.info(f"Total number of devices: {len(devices)}")
