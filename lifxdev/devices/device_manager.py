#!/usr/bin/env python3

import collections
import enum
import functools
import logging
import pathlib
import socket
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Union

import yaml

from lifxdev.colors import color
from lifxdev.devices import device
from lifxdev.devices import light
from lifxdev.devices import multizone
from lifxdev.devices import tile
from lifxdev.messages import packet
from lifxdev.messages import device_messages


CONFIG_PATH = pathlib.Path.home() / ".lifx" / "devices.yaml"


class DeviceConfigError(Exception):
    pass


class DeviceDiscoveryError(Exception):
    pass


class ProductInfo(NamedTuple):
    ip: str
    port: int
    label: str
    product_name: str
    device: light.LifxLight


class DeviceGroup:
    """Class for managing groups of devices"""

    def __init__(self, devices_and_groups: Dict[str, Any]):
        """Create a device group.

        Args:
            devices_and_groups: (dict) Dictionary containing devices and subgroups.
        """
        self._devices_and_groups = devices_and_groups

        # Get easy access to all devices in the device group
        self._all_devices: Dict[str, Any] = {}
        self._all_groups: Dict[str, Any] = {}
        for name, device_or_group in self._devices_and_groups.items():
            if isinstance(device_or_group, type(self)):
                self._all_groups[name] = device_or_group
                for sub_name, sub_device in device_or_group.get_all_devices().items():
                    self._all_devices[sub_name] = sub_device
                for sub_name, sub_group in device_or_group.get_all_groups().items():
                    self._all_groups[sub_name] = sub_group
            else:
                self._all_devices[name] = device_or_group

        # Organizing devices by type is useful for setting colormaps
        self._devices_by_type = collections.defaultdict(list)
        for lifx_device in self._all_devices.values():
            device_type = DeviceType[_DEVICE_TYPES_R[type(lifx_device).__name__]]
            self._devices_by_type[device_type].append(lifx_device)

    def get_all_devices(self) -> Dict[str, Any]:
        return self._all_devices

    def get_all_groups(self) -> Dict[str, "DeviceGroup"]:
        return self._all_groups

    def get_device(self, name: str) -> Any:
        return self._all_devices[name]

    def get_group(self, name: str) -> "DeviceGroup":
        return self._all_groups[name]

    def has_device(self, name: str) -> bool:
        return name in self._all_devices

    def has_group(self, name: str) -> bool:
        return name in self._all_groups

    def set_color(self, hsbk: light.COLOR_T, duration_s: float) -> None:
        """Set the color of all lights in the device group.

        Args:
            hsbk: (color.Hsbk) Human-readable HSBK tuple.
            duration_s: (float) The time in seconds to make the color transition.
        """

        for target in self._all_devices.values():
            target.set_color(hsbk, duration_s, ack_required=False)

    def set_power(self, state: bool, duration_s: float) -> None:
        """Set power state on all lights in the device group.

        Args:
            state: (bool) True powers on the light. False powers it off.
            duration_s: (float) The time in seconds to make the color transition.
        """
        for target in self._all_devices.values():
            target.set_power(state, duration_s, ack_required=False)

    def set_colormap(
        self,
        cmap: Union[str, color.colors.Colormap],
        duration_s: float,
        *,
        kelvin: int = color.KELVIN,
        division: int = 2,
    ) -> None:
        """Set the device group to a matplotlib colormap.

        Args:
            cmap_name: (str) Name or object of a matplotlib colormap.
            duration_s: (float) The time in seconds to make the color transition.
            kelvin: Color temperature of white colors in the colormap.
            division: How much to subdivide the tiles (must be in [1, 2, 4]).
        """
        bulbs = self._devices_by_type[DeviceType.light]
        bulbs += self._devices_by_type[DeviceType.infrared]
        bulb_cmap = color.get_colormap(cmap, len(bulbs), kelvin, randomize=True)
        for bulb, cmap_color in zip(bulbs, bulb_cmap):
            bulb.set_color(cmap_color, duration_s, ack_required=False)

        for strip in self._devices_by_type[DeviceType.multizone]:
            strip.set_colormap(cmap, duration_s, kelvin=kelvin, ack_required=False)

        for block in self._devices_by_type[DeviceType.tile]:
            block.set_colormap(
                cmap,
                duration_s,
                kelvin=kelvin,
                division=division,
                ack_required=False,
            )


# Convienence for validating type names in config files
class DeviceType(enum.Enum):
    group = 0
    light = 1
    infrared = 2
    multizone = 3
    tile = 4


# Mapping and reverse mapping from config file type name to class
_DEVICE_TYPES = {
    "group": DeviceGroup,
    "light": light.LifxLight,
    "infrared": light.LifxInfraredLight,
    "multizone": multizone.LifxMultiZone,
    "tile": tile.LifxTile,
}
_DEVICE_TYPES_R = {value.__name__: key for key, value in _DEVICE_TYPES.items()}


def _require_config_loaded(function: Callable) -> Callable:
    """Require configuration to be loaded before calling a class method"""

    @functools.wraps(function)
    def _run(self, *args, **kwargs) -> Any:
        if not self._root_device_group:
            raise DeviceConfigError("Device config not loaded.")
        return function(self, *args, **kwargs)

    return _run


class DeviceManager(device.LifxDevice):
    """Device manager

    Class for device discovery and loading configs.
    """

    def __init__(
        self,
        config_path: Optional[Union[str, pathlib.Path]] = None,
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
            config_path: (str) Path to the device config.
        """
        super().__init__(
            ip="255.255.255.255",
            buffer_size=buffer_size,
            timeout=timeout,
            nonblock_delay=nonblock_delay,
            verbose=verbose,
            comm=comm,
        )

        self._config_path = config_path
        self._timeout = timeout

        # Load product identification
        products = pathlib.Path(__file__).parent / "products.yaml"
        with products.open() as f:
            product_list = yaml.safe_load(f).pop().get("products", [])

        # For easily recovering product info via get_product_class
        self._products: Dict[str, Any] = {}
        for product in product_list:
            self._products[product["pid"]] = product

        # Load config sets the self._root_device_group variable
        self._discovered_device_group: Optional[DeviceGroup] = None
        self._root_device_group: Optional[DeviceGroup] = None
        if not config_path:
            return
        if config_path.exists():
            self.load_config(config_path)

    @property
    def discovered(self) -> DeviceGroup:
        """The discovered group"""
        if not self._discovered_device_group:
            raise DeviceDiscoveryError("Device discovery has not been performed.")
        return self._discovered_device_group

    @property
    @_require_config_loaded
    def root(self) -> DeviceGroup:
        """The root device group"""
        return self._root_device_group

    def discover(self, num_retries: int = 10) -> List[ProductInfo]:
        """Discover devices on the network

        Args:
            num_retries: (int) Number of GetService calls made.
        """

        logging.info("Scanning for LIFX devices.")
        state_service_dict: Dict[str, packet.LifxResponse] = {}
        # Disabling the timeout speeds up discovery
        self._set_timeout(None)
        for ii in range(num_retries):
            if ii + 1 == num_retries:
                # Use a timeout on the last get_devices_on_network
                # to ensure no lingering packets
                self._set_timeout(self._timeout)
            search_responses = self.get_devices_on_network()
            for response in search_responses:
                ip = response.addr[0]
                state_service_dict[ip] = response

        self._set_timeout(None)
        logging.info("Getting device info for discovered devices.")
        device_dict: Dict[str, ProductInfo] = {}
        for ip, state_service in state_service_dict.items():
            port = state_service.payload["port"]
            try:
                label = self.get_label(ip, port=port)
                product_dict = self.get_product_info(ip, port=port)
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
                    label=label,
                    comm=self._get_socket(),
                    timeout=self._timeout,
                    verbose=self._verbose,
                ),
            )
            device_dict[label] = product_info

        return device_dict

    def get_devices_on_network(self) -> List[packet.LifxResponse]:
        """Get device info from one or more devices.

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
        verbose: bool = False,
    ) -> str:
        """Get the label of a device

        Args:
            ip: (str) Override the IP address.
            port: (int) Override the UDP port.
            mac_addr: (str) Override the MAC address.
            verbose: (bool) Use logging.info instead of logging.debug.
        """
        return (
            self.send_recv(
                device_messages.GetLabel(),
                res_required=True,
                ip=ip,
                port=port,
                mac_addr=mac_addr,
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
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """Get the Python class needed to control a LIFX product.

        Args:
            ip: (str) Override the IP address.
            port: (int) Override the UDP port.
            mac_addr: (str) Override the MAC address.
            verbose: (bool) Use logging.info instead of logging.debug.
        """
        product_id = (
            self.send_recv(
                device_messages.GetVersion(),
                res_required=True,
                ip=ip,
                port=port,
                mac_addr=mac_addr,
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

    def load_config(self, config_path: Union[str, pathlib.Path]) -> DeviceGroup:
        """Load a config and populate device groups.

        Args:
            config_path: (str) Path to the device config.
        """
        config_path = pathlib.Path(config_path)
        with config_path.open() as f:
            config_dict = yaml.safe_load(f)

        self._root_device_group = self._load_device_group(config_dict)

    def _load_device_group(self, config_dict: Dict[str, Any]) -> DeviceGroup:
        """Recursively load a device group from a config dict."""
        devices_and_groups: Dict[str, Any] = {}
        for name, conf in config_dict.items():
            # Validate the type name
            type_name = conf.get("type")
            if not type_name:
                raise DeviceConfigError(f"Device/group {name!r} missing 'type' field.")
            try:
                device_type = DeviceType[type_name]
            except KeyError:
                raise DeviceConfigError(f"Invalid type for device {name!r}: {type_name}")

            # Check that the IP address is present
            ip = conf.get("ip")
            if not (ip or device_type == DeviceType.group):
                raise DeviceConfigError(f"Device {name!r} has no IP address.")

            # Recurse through group listing
            if device_type == DeviceType.group:
                group_devices = conf.get("devices")
                devices_and_groups[name] = self._load_device_group(group_devices)

            else:
                mac = conf.get("mac")
                port = conf.get("port", packet.LIFX_PORT)
                klass = _DEVICE_TYPES[device_type.name]
                devices_and_groups[name] = klass(
                    ip,
                    port=port,
                    label=name,
                    mac_addr=mac,
                    comm=self._get_socket(),
                    verbose=self._verbose,
                )

        return DeviceGroup(devices_and_groups)

    @_require_config_loaded
    def get_all_devices(self) -> Dict[str, Any]:
        return self._root_device_group.get_all_devices()

    @_require_config_loaded
    def get_all_groups(self) -> Dict[str, DeviceGroup]:
        return self._root_device_group.get_all_groups()

    @_require_config_loaded
    def get_device(self, name: str) -> Any:
        """Get a device by its label."""
        return self._root_device_group.get_device(name)

    @_require_config_loaded
    def get_group(self, name: str) -> DeviceGroup:
        """Get a group by its label."""
        return self._root_device_group.get_group(name)

    @_require_config_loaded
    def has_device(self, name: str) -> bool:
        """Check if a device exists."""
        return self._root_device_group.has_device(name)

    @_require_config_loaded
    def has_group(self, name: str) -> bool:
        """Check if a group exists."""
        return self._root_device_group.has_group(name)


if __name__ == "__main__":
    import coloredlogs

    coloredlogs.install(level=logging.INFO, fmt="%(asctime)s %(levelname)s %(message)s")

    device_manager = DeviceManager()
    devices = device_manager.discover()
    for device_info in sorted(devices.values(), key=lambda d: d.ip):
        product = device_info.product_name
        ip = device_info.ip
        label = device_info.label
        logging.info(f"{ip}:\tDiscovered {product}: {label}")
    logging.info(f"Total number of devices: {len(devices)}")
