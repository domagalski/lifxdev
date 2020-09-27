#!/usr/bin/env python3

"""Create a mock socket that can be used for testing/simulating"""

from typing import Dict, Optional, Tuple

from lifxdev.messages import packet

# These are needed to populate the packet internal responses
from lifxdev.messages import device_messages  # noqa: F401
from lifxdev.messages import light_messages  # noqa: F401
from lifxdev.messages import multizone_messages  # noqa: F401
from lifxdev.messages import tile_messages  # noqa: F401
from lifxdev.messages import firmware_effects  # noqa: F401


class MockSocket:
    """Mock the socket send/recv functions"""

    def __init__(self, *args, **kwargs):
        self._response_bytes = b""
        self._last_addr = ("", 0)
        self._blocking = True
        self._timeout = None
        self._responses: Dict[str, bytes] = {}
        for msg_num in sorted(packet._MESSAGE_TYPES.keys()):
            klass = packet._MESSAGE_TYPES[msg_num]
            name = klass.name
            self._responses[name], _ = packet.PacketComm.get_bytes_and_source(
                payload=klass(),
                res_required=True,
            )

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

        # usually, replacing get/set with state, but there are exceptions
        response_name = payload.name.replace("Get", "State").replace("Set", "State")
        if payload.name in ["GetColor", "SetColor", "SetWaveform"]:
            response_name = "State"
        elif payload.name == "EchoRequest":
            response_name = "EchoResponse"

        # Update the color message when setting the power level
        if payload.name == "SetPower":
            state_payload = packet.PacketComm.decode_bytes(self._responses["State"], addr).payload
            state_payload["power"] = payload["level"]
            self._responses["State"], _ = packet.PacketComm.get_bytes_and_source(
                payload=state_payload,
                res_required=True,
            )

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
            self._responses[response_name], _ = packet.PacketComm.get_bytes_and_source(
                payload=response_payload,
                res_required=True,
            )

        # Set the response. If an acknowledgement as been requested, use those bytes.
        if full_packet.frame_address["ack_required"]:
            self._response_bytes = self._responses["Acknowledgement"]
        else:
            self._response_bytes = self._responses[response_name]
        return len(message_bytes)

    def recvfrom(self, buffer_size) -> Tuple[bytes, Tuple[str, int]]:
        """Get the latest response bytes"""
        if self._blocking:
            return (self._response_bytes, self._last_addr)
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
