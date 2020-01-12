#!/usr/bin/env python3

import os
import json
import socket
import struct
import logging
from functools import reduce

import yaml
from matplotlib import cm

from .packet import LIFXpacket, RESPONSE_TYPES
from .exceptions import LIFXDeviceConfigError

logger = logging.getLogger(__name__)  # .addHandler(logging.NullHandler())
logger.setLevel("CRITICAL")

MAX_ZONES = 82
MAX_TILES = 16
TILE_SIZE = 64
SOCKET_TIMEOUT = 1
DEFAULT_PORT = 56700
DEFAULT_CONFIG = os.path.join(os.environ["HOME"], ".lifx/device_config.yaml")

WAVEFORMS = {
    "SAW": 0,
    "saw": 0,
    "SINE": 1,
    "sine": 1,
    "HALF_SINE": 2,
    "half_sine": 2,
    "TRIANGLE": 3,
    "triangle": 3,
    "PULSE": 4,
    "pulse": 4,
}

APPLICATION_REQUEST = {"NO_APPLY": 0, "no_apply": 0, "APPLY": 1, "apply": 1, "APPLY_ONLY": 2, "apply_only": 2}


class LIFXdevice(LIFXpacket):
    """
    Basic LIFX device class. All devices inherit from this.
    """

    def __init__(self, target, ip, port=DEFAULT_PORT, do_init_socket=False, broadcast=False):
        """
        Initialize a LIFX device.

        Input:
            target          Mac address of the device, either a str or int.
            ip              IP address of the device.
            port            UDP port. Defaults to 56700.
            do_init_socket  Whether to initialize the socket (default: False).
            broadcast       Whether or not to connect to a broadcast device.
        """
        super(LIFXdevice, self).__init__()
        if isinstance(target, str):
            target = mac_str_to_int(target)

        self.target = target
        self.ip = ip
        self.port = port
        self.device_type = None

        if do_init_socket:
            self.init_socket(broadcast)
        else:
            self.sock = None

    def init_socket(self, broadcast=False):
        """
        Initialize the network socket.
        """
        # Network socket initialization
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(SOCKET_TIMEOUT)
        if broadcast:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.sock.bind(("", 0))

    def get_all_cmaps(self):
        # put all cmaps into a list
        cmap_names = [name for name in cm.cmap_d.keys() if name[-2:] != "_r"]
        cmap_names += [name for name in cm.cmaps_listed.keys() if name[-2:] != "_r"]
        cmap_names = list(set(cmap_names))
        return cmap_names

    def get_device_attrs(self, product_filename):
        """
        Get the device label from the device and the product from a
        json file with the LIFX product information.

        Input:
            product_filename    LIFX product json.
        """
        label = self.get_label()
        product = self.get_product(product_filename)
        if label is None or product is None:
            return None
        else:
            return (label, product)

    def get_label(self):
        """
        Get the device label from the device and return it.
        """
        # Parse the payload to get the product
        response = self.get_validated_response("GetLabel")
        if response is None:
            return

        header, payload = response
        label = payload.rstrip(b"\x00").decode()
        return label

    def get_power(self):
        """
        Get whether or not the device is powered on (bool).
        """
        header, payload = self.get_validated_response("GetPowerDevice")
        light_powered = bool(struct.unpack("<H", payload)[0])
        return light_powered

    def get_product(self, product_filename):
        """
        Get the product information for the device.
        """
        with open(product_filename) as f:
            products = json.load(f)[0]["products"]

        # Parse the payload to get the product
        response = self.get_validated_response("GetVersion")
        if response is None:
            return

        header, payload = response
        vendor, product, version = struct.unpack("<III", payload)
        for prod in products:
            if product == prod["pid"]:
                return prod

    def get_validated_response(self, msg_type, send_msg=True):
        """
        Greate a Get request and validate the response is expected.

        Input:
            msg_type:   string. The type of message to get.
            send_msg:   bool. Send the message before waiting for responses.

        Return:
            header (dict)
            payload (bytes)
        """
        # create the packet and send it to the bulb
        if send_msg:
            self.generate_packet(msg_type, mac_addr=self.target, res_required=True)
            header, payload = self.parse_packet(self.send_and_recv())
        else:
            header, payload = self.parse_packet(self.sock.recv(4096))
        if header is None:
            logger.error("ERROR: Cannot receive packets: {}".format(payload))
            return None

        # Packet type must match expected response
        if header["type"] != RESPONSE_TYPES[msg_type.replace("Get", "State")]:
            raise RuntimeError("Response type mismatch.")
        return header, payload

    def generate_and_send(self, msg_type, ack_required=False, res_required=False):
        """
        Generate a packet for a certain Get message type and send it.

        Input:
            msg_type:   string. The type of message to send
        """
        self.generate_packet(msg_type, self.target, ack_required, res_required)
        self.sock.sendto(self.packet, (self.ip, self.port))
        self.reset_packet()

    def ping_device(self):
        response = self.get_validated_response("GetService")
        can_reach = bool(response is not None)
        return can_reach

    def send_and_recv(self):
        """
        Send a packet and get a single response.
        """
        if self.packet is None:
            raise RuntimeError("no packet")

        self.sock.sendto(self.packet, (self.ip, self.port))
        try:
            resp_bytes = self.sock.recv(4096)
        except socket.timeout:
            resp_bytes = None
        self.reset_packet()
        return resp_bytes

    def set_power(self, light_powered, duration_ms):
        """
        Set the power state on the device (True/False).
        """
        power = 65535 * bool(light_powered)
        self.payload = struct.pack("<HI", power, duration_ms)
        self.generate_and_send("SetPowerDevice")


# Broadcast device for discovery
class DeviceManager(LIFXdevice):
    """
    Broadcast discovery class.
    """

    def __init__(self):
        """
        Initialize a LIFX device as an untargeted device with a
        broadcast address.
        """
        super(DeviceManager, self).__init__(0, "255.255.255.255", broadcast=True, do_init_socket=True)
        self.device_type = "manager"

        # get the products file from the lifx github
        products = os.path.join(os.environ["HOME"], ".lifx/products.json")
        if not os.path.exists(products):
            os.system("mkdir -pv {}".format(os.path.dirname(products)))
            product_url = "https://raw.githubusercontent.com/LIFX/products/master/products.json"
            wget_cmd = "wget {} -O {}".format(product_url, products)
            if os.system(wget_cmd):
                raise RuntimeError("Cannot get product file from LIFX.")
        self.lifx_product_filename = products

        # managed devices and groups
        self.discovery_devices = {}
        self.devices = {}
        self.groups = {}

        # self.init_socket(True)

    def discover(self, max_attempts=1):
        """
        Discover LIFX devices. By default, this loops through devices
        once, but the parameter max_attempts can be set to implement
        retry logic if necessary.
        """
        devices = {}
        do_retry = True
        attempts = 0
        while do_retry and attempts < max_attempts:
            do_retry = False
            # generate the packet to broadcast
            self.generate_packet("GetService", res_required=True)
            try:
                self.sock.sendto(self.packet, (self.ip, self.port))
            except PermissionError:
                logger.error("Resetting socket.")
                self.sock.close()
                # time.sleep(1)

                # Try to reset the packet
                self.init_socket(True)
                do_retry = True
                continue
            logger.info("Discovery attempt {}.".format(attempts + 1))

            # Get StateService responses from devices
            recv_packets = True
            while recv_packets:
                recv_packets, dev_info = self.recv_state_service()

                # Skip if error getting StateService
                if dev_info is None:
                    logger.error("ERROR: Cannot get device info.")
                    do_retry = True
                    continue

                response = self.get_targeted_device(*dev_info)

                # retry on error scanning
                if response is None:
                    logger.error("ERROR: Cannot get device label.")
                    do_retry = True
                    continue

                label, device_type = response

                # skip invalid devices
                if device_type is None:
                    continue

                # Skip duplicates
                if label in devices:
                    continue

                new_device = device_type(*dev_info, do_init_socket=True)
                if new_device.ping_device():
                    devices[label] = device_type(*dev_info)
                else:
                    logger.error("ERROR: Cannot initialize device.")
                    do_retry = True
            attempts += 1

        self.sock.close()
        self.discovery_devices = devices
        return devices

    def get_group_devices(self, group_name):
        """
        Get a list of devices in a device group.
        """
        device_list = []
        group = self.groups[group_name]
        for dev_name, dev_type in group:
            if dev_type == "group":
                device_list += self.get_group_devices(dev_name)
            else:
                device_list.append(dev_name)
        return device_list

    def get_targeted_device(self, target, ip, port):
        """
        Get a device based on mac address, ip, and port.
        Return an object corresponding to device type.
        """
        device = LIFXdevice(target, ip, port, True)
        dev_attrs = device.get_device_attrs(self.lifx_product_filename)
        if dev_attrs is None:
            return (None, None)

        # get the object corresponding to the features
        label, product = dev_attrs
        features = product["features"]
        if features["chain"]:
            dev_type = LIFXtile
        elif features["multizone"]:
            dev_type = LIFXmultizone
        else:
            dev_type = LIFXbulb
        return (label, dev_type)

    def init_from_devices(self, device_name, do_init_socket=True):
        device = self.devices[device_name]
        if do_init_socket:
            device.init_socket()
        return device

    def init_from_ipaddr(self, target, ip, dev_type, port=DEFAULT_PORT):
        pass

    def load_config(self, config_filename=DEFAULT_CONFIG, do_init_socket=False):
        """
        Load devices and groups from a yaml device configuration file.
        """
        with open(config_filename) as f:
            device_dict = yaml.safe_load(f)

        self.populate_from_dict(device_dict, do_init_socket)

    def populate_from_dict(self, device_dict, do_init_socket=False):
        """
        Recursive function that populates the self.devices and
        self.groups dictionaries with a device list and group tree.
        """
        for name in device_dict:
            if "type" not in device_dict[name]:
                raise LIFXDeviceConfigError(
                    "The 'type' field is missing from device/group: '{}'".format(name)
                )

            # recursive case is a device group
            if device_dict[name]["type"] == "group":
                if "devices" not in device_dict[name]:
                    raise LIFXDeviceConfigError(
                        "The 'devices' field is missing from group: '{}'".format(name)
                    )

                self.groups[name] = []
                for device in device_dict[name]["devices"]:
                    # get the name and device type
                    dev_name = list(device.keys())[0]
                    dev_type = device[dev_name]["type"]

                    # recurse
                    self.groups[name].append((dev_name, dev_type))
                    self.populate_from_dict(device, do_init_socket)

            # base case is an individual device
            else:
                for key in ["ip", "mac"]:
                    if key not in device_dict[name]:
                        raise LIFXDeviceConfigError(
                            "The '{}' field is missing from device: '{}'".format(key, name)
                        )

                mac = device_dict[name]["mac"]
                ip = device_dict[name]["ip"]
                device_class = get_device_class(device_dict[name]["type"])
                self.devices[name] = device_class(mac, ip, do_init_socket=do_init_socket)

    def recv_state_service(self):
        """
        Get a state service message and validate it.

        Return (True if not timed out, device_info)
        """
        try:
            packet, addr = self.sock.recvfrom(4096)
            is_dev, dev_info = self.state_service(packet, addr)
            if is_dev:
                return (True, dev_info)
            else:
                return (True, None)
        except socket.timeout:
            return (False, None)

    def state_service(self, packet, addr):
        """
        Check if message is a StateService packet and parse its values.
        """
        header, payload = self.parse_packet(packet)

        # Magic number: StateService == 3
        if header["type"] != 3:
            return (False, "mismatch:type")

        service, port = struct.unpack("<BI", payload)
        if port:
            return (True, (header["target"], addr[0], port))
        else:
            return (False, "device:unavailable")


# Basic LIFX bulb class
class LIFXbulb(LIFXdevice):
    """
    The LIFX bulb base class. Basic light device operations are
    defined in this class.
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize the bulb with its mac address, IP address, and port.
        """
        super(LIFXbulb, self).__init__(*args, **kwargs)
        self.device_type = "bulb"

    def get_state(self):
        """
        Get the bulb state.

        return tuple items:
            hsbk:   hue, saturation, brightness, kelvin tuple
            power:  power state
            label:  device label
        """
        # create the packet and send it to the bulb
        header, payload = self.get_validated_response("Get")

        # unpack values from the packets.
        bulb_state = struct.unpack("<HHHH h H 32s Q", payload)
        hsbk = hsbk_human(bulb_state[:4])
        _, power, label, _ = bulb_state[4:]
        label = label.rstrip(b"\x00").decode()
        power = bool(power)

        return (hsbk, power, label)

    def get_power(self):
        """
        Get whether or not the device is powered on (bool).
        """
        header, payload = self.get_validated_response("GetPowerLight")
        light_powered = bool(struct.unpack("<H", payload)[0])
        return light_powered

    def get_infrared(self):
        """
        not implemented
        """
        raise RuntimeError("not implemented")

    def set_color(self, hsbk, duration_ms):
        """
        Set the color of a bulb

        Input:
            hsbk            hue, sat, brightness, kelvin tuple
            duration_ms     fade in time in milliseconds
        """
        hue, sat, brightness, kelvin = hsbk_machine(hsbk)
        self.payload = struct.pack("<BHHHHI", 0, hue, sat, brightness, kelvin, duration_ms)
        self.generate_and_send("SetColor")

    def set_waveform(self, transient, hsbk, period, cycles, skew_ratio, waveform):
        """
        Set the waveform. See https://lan.developer.lifx.com/v2.0/docs/waveforms
        for details on the inputs

        Input:
            transient (bool)
            hsbk (tuple)
            period (milliseconds, int)
            cycles (float)
            skew_ratio (float)
            waveform (string)
        """
        transient_bytes = struct.pack("<BB", 0, bool(transient))

        hue, sat, brightness, kelvin = hsbk_machine(hsbk)
        hsbk_bytes = struct.pack("<HHHH", hue, sat, brightness, kelvin)

        waveform_int = WAVEFORMS[waveform]
        if waveform_int == 4:
            if skew_ratio:
                skew_scaled = int(65535 * (skew_ratio - 0.5))
            else:
                skew_scaled = -32768
        else:
            skew_scaled = 0
        wave_bytes = struct.pack("<IfhB", period, cycles, skew_scaled, waveform_int)

        self.payload = transient_bytes + hsbk_bytes + wave_bytes
        self.generate_and_send("SetWaveform")

    def set_power(self, light_powered, duration_ms):
        """
        Set the power state on the device (True/False).
        """
        power = 65535 * bool(light_powered)
        self.payload = struct.pack("<HI", power, duration_ms)
        self.generate_and_send("SetPowerLight")

    def set_infrared(self):
        """
        do not use
        """
        raise RuntimeError("not implemented")


class _LIFXeffects(LIFXbulb):
    """
    Common firmware effects for Z, Beam, and Tile
    """

    pass


class LIFXmultizone(_LIFXeffects):
    """
    Class for Z strips and Beam devices
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize the bulb with its mac address, IP address, and port.
        """
        super(LIFXmultizone, self).__init__(*args, **kwargs)
        self.device_type = "multizone"
        self.n_zones = 0

    def get_extended_color_zones(self):
        """
        Get the extended color zone info with the new API
        https://lan.developer.lifx.com/docs/multizone-messages

        Return: see web documentation for more info
            n_zones (count)
            index
            colors_count
            hsbk_list[82]
        """
        response = self.get_validated_response("GetExtendedColorZones")
        if response is None:
            return (None, None, None, None)
        header, payload = response

        # unpack values from the packets.
        multi_state = struct.unpack("<HHB" + MAX_ZONES * "HHHH" + "B", payload)
        n_zones = multi_state[0]
        index = multi_state[1]
        color_count = multi_state[2]

        # convert hsbk
        hsbk_list = [hsbk_human(multi_state[3 + 4 * i : 3 + 4 * (i + 1)]) for i in range(MAX_ZONES)]  # noqa

        self.n_zones = n_zones
        return (n_zones, index, color_count, hsbk_list)

    def set_extended_color_zones(self, duration, application, index, colors_count, hsbk_list):
        """
        Set the extended color zone info with the new API
        https://lan.developer.lifx.com/docs/multizone-messages

        Input:
            duration (milliseconds)
            appication request
            index
            colors_count
            hsbk_list[82]
        """
        # Convert the color list to one long tuple
        hsbk_list = [hsbk_machine(hsbk) for hsbk in hsbk_list]
        hsbk_tuple = reduce(lambda t1, t2: t1 + t2, hsbk_list)

        # Generate the payload and apply it to the device
        apply_int = APPLICATION_REQUEST[application]
        struct_tuple = (duration, apply_int, index, colors_count) + hsbk_tuple
        self.payload = struct.pack("<IBHB" + MAX_ZONES * "HHHH", *struct_tuple)
        self.generate_and_send("SetExtendedColorZones")

    def set_cmap(self, cmap_name, duration=0, roll_offset=0):
        if not self.n_zones:
            self.get_extended_color_zones()

        kelvin = 5500

        cmap = cm.get_cmap(cmap_name, self.n_zones)

        # light up the beam
        hsbk_list = []
        for i in range(self.n_zones):
            hsbk_list.append(rgba2hsbk(cmap((i + roll_offset) % self.n_zones), kelvin))

        for i in range(self.n_zones, MAX_ZONES):
            hsbk_list.append((0, 0, 0, 0))

        # normalize brightness
        max_bright = max([hsbk[2] for hsbk in hsbk_list])
        if max_bright:
            hsbk_list = [(hsbk[0], hsbk[1], hsbk[2] / max_bright, hsbk[3]) for hsbk in hsbk_list]

        self.set_extended_color_zones(duration, "APPLY", 0, self.n_zones, hsbk_list)


class LIFXtile(_LIFXeffects):
    """
    Class for Tile devices
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize the bulb with its mac address, IP address, and port.
        """
        super(LIFXtile, self).__init__(*args, **kwargs)
        self.device_type = "tile"

    def tile_msg(self, msg_tuple):
        """
        Get the parameters of a tile message into a dictionary.
        https://lan.developer.lifx.com/docs/tile-messages
        See message field data types.
        """
        msg_dict = {}
        msg_dict["accel_meas_x"] = msg_tuple[0]
        msg_dict["accel_meas_y"] = msg_tuple[1]
        msg_dict["accel_meas_z"] = msg_tuple[2]
        msg_dict["user_x"] = msg_tuple[4]
        msg_dict["user_y"] = msg_tuple[5]
        msg_dict["width"] = msg_tuple[6]
        msg_dict["height"] = msg_tuple[7]
        msg_dict["device_version_vender"] = msg_tuple[9]
        msg_dict["device_version_product"] = msg_tuple[10]
        msg_dict["device_version_version"] = msg_tuple[11]
        msg_dict["firmware_build"] = msg_tuple[12]
        msg_dict["firmware_version"] = msg_tuple[14]
        return msg_dict

    def get_device_chain(self):
        """
        Get information about the color zones

        Returns a list of message dicts from the tile_msg function.
        """
        header, payload = self.get_validated_response("GetDeviceChain")
        tile_fmt = "hhhhffBBBIIIQQII"
        msg_size = len(tile_fmt)

        # unpack values from the packets.
        tile_state = struct.unpack("<B" + MAX_TILES * tile_fmt + "B", payload)
        start_index = tile_state[0]
        total_count = tile_state[-1]

        # extract the tile messages
        tile_flat = tile_state[1 + start_index : 1 + start_index + total_count * msg_size]  # noqa
        tile_msgs = [
            self.tile_msg(tile_flat[i * msg_size : (i + 1) * msg_size]) for i in range(total_count)  # noqa
        ]
        return tile_msgs

    def get_tile_state(self, n_tiles, tile_index=0):
        """
        Get the state of a number of tiles.

        Default the x, y, and width to 0, 0, and 8.
        """
        self.payload = struct.pack("<BBBBBB", tile_index, n_tiles, 0, 0, 0, 8)
        self.generate_and_send("GetTileState64", res_required=True)

        # TODO handle timeouts
        # assume asyncronous
        tile_states = [None for i in range(n_tiles)]
        for i in range(n_tiles):
            idx, hsbk_list = self._recv_tile_state()
            tile_states[idx] = hsbk_list
        return tile_states

    def _recv_tile_state(self):
        """
        Get the tile state, assuming it is available
        """
        # TODO handle timeouts
        header, payload = self.get_validated_response("GetTileState64", False)
        tile_vals = struct.unpack("<BBBBB" + TILE_SIZE * "HHHH", payload)

        tile_index = tile_vals[0]
        hsbk_list = [hsbk_human(tile_vals[5 + 4 * i : 5 + 4 * (i + 1)]) for i in range(TILE_SIZE)]  # noqa
        return (tile_index, hsbk_list)

    def set_tile_state(self, tile_index, length, duration, hsbk_list):
        """
        Set the tile state for a single tile
        """
        # TODO make this multiple tiles
        hsbk_list = [hsbk_machine(hsbk) for hsbk in hsbk_list]
        hsbk_tuple = reduce(lambda t1, t2: t1 + t2, hsbk_list)

        # Generate the payload and apply it to the device
        struct_tuple = (tile_index, length, 0, 0, 0, 8, duration) + hsbk_tuple
        self.payload = struct.pack("<BBBBBBI" + TILE_SIZE * "HHHH", *struct_tuple)
        self.generate_and_send("SetTileState64")

    def set_user_position(self, tile_index, user_x, user_y):
        """
        Set the position of a tile.
        """
        self.payload = struct.pack("<BHff", tile_index, 0, user_x, user_y)
        self.generate_and_send("SetUserPosition")


def get_device_class(device_type):
    if device_type == "bulb":
        return LIFXbulb
    elif device_type == "multizone":
        return LIFXmultizone
    elif device_type == "tile":
        return LIFXtile
    else:
        raise ValueError("Invalid device type: {}".format(device_type))


def hsbk_human(hsbk):
    """
    Make hsbk human readable
    """
    hue, sat, brightness, kelvin = hsbk
    hue *= 360.0 / 65535.0
    sat /= 65535.0
    brightness /= 65535.0
    return (hue, sat, brightness, kelvin)


def hsbk_machine(hsbk):
    """
    Make hsbk machine readable
    """
    hue, sat, brightness, kelvin = hsbk
    hue = int(hue * 65535 / 360.0) % 65535
    sat = int(sat * 65535)
    brightness = int(brightness * 65535)
    kelvin = int(kelvin)
    return (hue, sat, brightness, kelvin)


def mac_int_to_str(mac_int):
    mac_size = 6  # number of bytes in mac address
    mac_hex = struct.pack("Q", mac_int)[:mac_size].hex()
    return ":".join([mac_hex[2 * i : 2 * i + 2] for i in range(mac_size)])  # noqa


def mac_str_to_int(mac_str):
    # Swap endianness, then convert to an integer
    hex_str = "0x" + "".join(reversed(mac_str.split(":")))
    return int(hex_str, 16)


def rgba2hsbk(rgba_tuple, kelvin):
    """
    Convert RGBA to HSBK.

    Assume max(rgba) == 1

    kelvin mainly sets white balance for photography.
    """
    red, green, blue, alpha = rgba_tuple
    max_col = max(red, green, blue)
    min_col = min(red, green, blue)

    # Get the hue
    hue = 0
    h_scale = 60.0
    if max_col == min_col:
        hue = 0.0
    elif max_col == red:
        hue = h_scale * ((green - blue) / (max_col - min_col))
    elif max_col == green:
        hue = h_scale * (2 + (blue - red) / (max_col - min_col))
    elif max_col == blue:
        hue = h_scale * (4 + (red - green) / (max_col - min_col))

    # Fix wrapping for hue
    while hue > 360:
        hue -= 360
    while hue < 0:
        hue += 360

    # get the saturation
    sat = 0.0
    if max_col:
        sat = (max_col - min_col) / max_col

    # brightness
    brightness = max_col

    return (hue, sat, brightness, kelvin)
