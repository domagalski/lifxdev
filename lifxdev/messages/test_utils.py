#!/usr/bin/env python3

"""Create a mock socket that can be used for testing/simulating"""

import enum
import socket
from typing import Dict, Optional, Tuple

from lifxdev.messages import packet

# These are needed to populate the packet internal responses
from lifxdev.messages import device_messages  # noqa: F401
from lifxdev.messages import light_messages  # noqa: F401
from lifxdev.messages import multizone_messages  # noqa: F401
from lifxdev.messages import tile_messages  # noqa: F401
from lifxdev.messages import firmware_effects  # noqa: F401


# Take from the product info page:
# https://lan.developer.lifx.com/v2.0/docs/lifx-products
class Product(enum.Enum):
    NONE = 0
    LIGHT = 27
    IR = 29
    MZ = 38
    TILE = 55


class MockSocket:
    """Mock the socket send/recv functions"""

    def __init__(
        self,
        *args,
        label: str = "LIFX mock",
        mac_addr: Optional[str] = None,
        product: Product = Product.NONE,
        **kwargs,
    ):
        self._label = label
        self._mac_addr = mac_addr
        self._response_bytes = b""
        self._last_addr = ("", 0)
        self._blocking = True
        self._timeout = None
        self._sequence = 0
        self._first_response_query = False
        self._responses: Dict[str, bytes] = {}
        for msg_num in sorted(packet._MESSAGE_TYPES.keys()):
            message = packet._MESSAGE_TYPES[msg_num]()
            name = message.name

            # Set up some defaults
            if name in ["State", "StateLabel"]:
                message["label"] = self._label
            elif name == "StateDeviceChain":
                message["total_count"] = 5
                for ii, tile in enumerate(message["tile_devices"]):
                    tile = message["tile_devices"][ii]
                    tile["width"] = 8
                    tile["height"] = 8
                    message["tile_devices"][ii] = tile
            elif name == "StateExtendedColorZones":
                message["count"] = 32
                message["colors_count"] = 32
            elif name == "StateService":
                message["service"] = 1
                message["port"] = packet.LIFX_PORT
            elif name == "StateVersion":
                message["vendor"] = 1
                message["product"] = product.value

            self._responses[name], self._source = packet.PacketComm.get_bytes_and_source(
                payload=message,
                mac_addr=self._mac_addr,
                res_required=True,
            )

    def set_label(self, label: str, addr: Tuple[str, int] = ("127.0.0.1", packet.LIFX_PORT)):
        """Set the label returned in messages"""
        self.update_payload("State", addr, label=label)
        self.update_payload("StateLabel", addr, label=label)

    def set_product(
        self, product: Product, addr: Tuple[str, int] = ("127.0.0.1", packet.LIFX_PORT)
    ):
        """Set the product returned in messages"""
        self.update_payload("StateVersion", addr, product=product.value)

    def update_payload(self, register_name: str, addr: Tuple[str, int], **kwargs):
        """Update a payload's bytes registers"""
        payload = packet.PacketComm.decode_bytes(self._responses[register_name], addr).payload
        for key, value in kwargs.items():
            payload[key] = value
        self._responses[register_name], self._source = packet.PacketComm.get_bytes_and_source(
            payload=payload,
            mac_addr=self._mac_addr,
            source=self._source,
            sequence=self._sequence,
        )

    def setsockopt(self, *args, **kwargs):
        """Ignore setsockopt calls"""
        pass

    def getblocking(self) -> bool:
        """Return the blocking status"""
        return self._blocking

    def gettimeout(self) -> Optional[float]:
        """Return the timeout"""
        return self._timeout

    def setblocking(self, flag: bool):
        """Set the blocking flag"""
        self._blocking = flag

    def settimeout(self, timeout: Optional[float]):
        """Set the timeout"""
        self._timeout = timeout

    def sendto(self, message_bytes: bytes, addr: Tuple[str, int]):
        """Mock sendto by spoofing the bytes to be returned on the next recvfrom"""
        self._last_addr = addr

        full_packet = packet.PacketComm.decode_bytes(message_bytes, addr)
        payload = full_packet.payload
        self._source = full_packet.frame["source"]
        self._sequence = full_packet.frame_address["sequence"]

        # usually, replacing get/set with state, but there are exceptions
        response_name = payload.name.replace("Get", "State").replace("Set", "State")
        if payload.name in ["GetColor", "SetColor", "SetWaveform"]:
            response_name = "State"
        elif payload.name == "EchoRequest":
            response_name = "EchoResponse"

        # Update the color message when setting the power level
        if payload.name == "SetPower":
            self.update_payload("State", addr, power=payload["level"])

        # Craft a response when setting light state.
        if payload.name.startswith("Set") or payload.name == "EchoRequest":
            response_payload = packet.PacketComm.decode_bytes(
                self._responses[response_name], addr
            ).payload
            payload_registers = set([rr[0] for rr in payload.registers])
            response_registers = set([rr[0] for rr in response_payload.registers])
            intersection = response_registers & payload_registers
            for name in intersection:
                response_payload[name] = payload[name]
            if response_name == "StateExtendedColorZones":
                response_payload["count"] = response_payload["colors_count"]
            self._responses[response_name], self._source = packet.PacketComm.get_bytes_and_source(
                payload=response_payload,
                mac_addr=self._mac_addr,
                source=self._source,
                sequence=self._sequence,
            )

        # Set the response. If an acknowledgement as been requested, use those bytes.
        if full_packet.frame_address["ack_required"]:
            self._response_bytes = self._responses["Acknowledgement"]
        else:
            self._response_bytes = self._responses[response_name]
        self._first_response_query = True
        return len(message_bytes)

    def recvfrom(self, buffer_size) -> Tuple[bytes, Tuple[str, int]]:
        """Get the latest response bytes"""
        if self._blocking and self._first_response_query:
            self._first_response_query = False
            return (self._response_bytes, self._last_addr)
        elif self._timeout:
            raise socket.timeout
        else:
            raise BlockingIOError


if __name__ == "__main__":
    import coloredlogs
    import logging

    coloredlogs.install(level=logging.INFO)

    udp_sender = packet.UdpSender(ip="127.0.0.1", comm=MockSocket())
    packet_comm = packet.PacketComm(udp_sender, verbose=True)
    set_color = light_messages.SetColor(
        color=packet.Hsbk(
            hue=16384,
            saturation=65535,
            brightness=65535,
            kelvin=5500,
        )
    )

    logging.info(
        packet_comm.send_recv(payload=light_messages.SetPower(level=65535), res_required=True)
    )
    logging.info(packet_comm.send_recv(payload=set_color, res_required=True))
    logging.info(packet_comm.send_recv(payload=light_messages.SetPower(), ack_required=True))
    logging.info(packet_comm.send_recv(payload=light_messages.Get(), res_required=True))
