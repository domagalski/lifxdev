#!/usr/bin/env python3

import os
import struct


def _bytes_little_endian(num, n_bytes):
    hex_str = hex(num)[2:]
    hex_str = (n_bytes * 2 - len(hex_str)) * "0" + hex_str
    hex_list = [hex_str[2 * i : 2 * (i + 1)] for i in range(len(hex_str) // 2)][::-1]
    return "".join(hex_list)


MESSAGE_TYPES = {
    # Device messages
    "GetService": _bytes_little_endian(2, 2),
    "GetHostInfo": _bytes_little_endian(12, 2),
    "GetHostFirmware": _bytes_little_endian(14, 2),
    "GetWifiInfo": _bytes_little_endian(16, 2),
    "GetWifiFirmware": _bytes_little_endian(18, 2),
    "GetPowerDevice": _bytes_little_endian(20, 2),
    "SetPowerDevice": _bytes_little_endian(21, 2),
    "GetLabel": _bytes_little_endian(23, 2),
    "SetLabel": _bytes_little_endian(24, 2),
    "GetVersion": _bytes_little_endian(32, 2),
    "GetInfo": _bytes_little_endian(32, 2),
    "Acknowledgement": _bytes_little_endian(45, 2),
    "GetLocation": _bytes_little_endian(48, 2),
    "SetLocation": _bytes_little_endian(49, 2),
    "GetGroup": _bytes_little_endian(51, 2),
    "SetGroup": _bytes_little_endian(52, 2),
    "EchoRequest": _bytes_little_endian(58, 2),
    "EchoResponse": _bytes_little_endian(59, 2),
    # Light messages
    "Get": _bytes_little_endian(101, 2),
    "SetColor": _bytes_little_endian(102, 2),
    "SetWaveform": _bytes_little_endian(103, 2),
    "SetWaveformOptional": _bytes_little_endian(119, 2),
    "GetPowerLight": _bytes_little_endian(116, 2),
    "SetPowerLight": _bytes_little_endian(117, 2),
    # MultiZone (Z/Beam) messages
    "SetExtendedColorZones": _bytes_little_endian(510, 2),
    "GetExtendedColorZones": _bytes_little_endian(511, 2),
    # Tile messages
    "GetDeviceChain": _bytes_little_endian(701, 2),
    "SetUserPosition": _bytes_little_endian(703, 2),
    "GetTileState64": _bytes_little_endian(707, 2),
    "SetTileState64": _bytes_little_endian(715, 2),
}

RESPONSE_TYPES = {
    "StateService": 3,
    "StateHostInfo": 13,
    "StateHostFirmware": 15,
    "StateWifiInfo": 17,
    "StateWifiFirmware": 19,
    "StatePowerDevice": 22,
    "StateLabel": 25,
    "StateVersion": 33,
    "StateInfo": 33,
    "StateLocation": 50,
    "StateGroup": 53,
    "State": 107,
    "StatePowerLight": 118,
    "StateExtendedColorZones": 512,
    "StateDeviceChain": 702,
    "StateTileState64": 711,
}


class LIFXpacket(object):
    def __init__(self):
        self.reset_packet()
        # Must be nonzero
        self.source = _bytes_little_endian(os.getpid(), 4)

    def reset_packet(self):
        """
        Set the default values of a packet
        """
        # Default values
        self.msg_type = None
        self.msg_type_hex = None
        self.tagged = None
        self.size = 0
        self.frame_header = None
        self.frame_address = None
        self.protocol_header = None
        self.payload = None
        self.packet = None

    def generate_frame_header(self):
        """
        Must be called last
        """
        if self.tagged is None or self.size == 0:
            raise RuntimeError("Cannot generate frame header.")
        else:
            tagged = str(int(self.tagged))

        # 4 + 4 + 8 represents the size of the frame header
        size = _bytes_little_endian((self.size + 4 + 4 + 8) // 2, 2)
        header_list = [
            size,  # 0: size in bytes
            _bytes_little_endian(
                int(
                    "".join(
                        [
                            "0b",
                            "".join(
                                [
                                    "0" * 2,  # 1: origin: must be zero
                                    tagged,  # 2: tagged
                                    "1",  # 3: addressable. must be 1
                                    "010000000000",  # 4: protocol. must be 1024
                                ]
                            ),
                        ]
                    ),
                    2,
                ),
                2,
            ),
            self.source,
        ]  # 5: source, default 0, used in responses
        self.frame_header = "".join(header_list)
        return self.frame_header

    def generate_frame_address(self, mac_addr=0):
        if not self.ack_required and not self.res_required:
            self.sequence = "00"
        sequence = self.sequence

        mac_addr = _bytes_little_endian(mac_addr, 8)

        ack_required = str(int(self.ack_required))
        res_required = str(int(self.res_required))

        address_list = [
            mac_addr,  # 0: target: mac address of device
            "0" * 12,  # 1: reserved. all 0
            _bytes_little_endian(
                int(
                    "".join(
                        [
                            "0b",
                            "".join(
                                [
                                    "0" * 6,  # 2: reserved. all 0
                                    ack_required,  # 3: acknowledgement required (bool)
                                    res_required,  # 4: response required (bool)
                                ]
                            ),
                        ]
                    ),
                    2,
                ),
                1,
            ),
            sequence,
        ]  # 5: sequence
        self.frame_address = "".join(address_list)
        return self.frame_address

    def generate_protocol_header(self):
        protocol_header_list = [
            "0" * 16,  # 0: reserved
            self.msg_type_hex,  # 1: message type
            "0" * 4,
        ]  # 2: reserved
        self.protocol_header = "".join(protocol_header_list)
        return self.protocol_header

    def generate_packet(self, msg_type, mac_addr=None, ack_required=False, res_required=False, sequence="00"):
        """
        pass
        """
        try:
            self.msg_type_hex = MESSAGE_TYPES[msg_type]
            self.msg_type = msg_type
        except KeyError:
            print("ERROR: Invalid message type: {}".format(msg_type))
            return None

        self.ack_required = ack_required
        self.res_required = res_required
        self.sequence = sequence

        if mac_addr is None:
            mac_addr = 0
            self.tagged = True
        else:
            self.tagged = False
        self.generate_frame_address(mac_addr)
        self.generate_protocol_header()

        # Generate the header.
        self.size = len(self.frame_address) + len(self.protocol_header)
        if self.payload is not None:
            self.size += len(self.payload)
            payload_hex = self.payload.hex()
        else:
            payload_hex = ""
        self.generate_frame_header()

        self.packet = bytes.fromhex(
            "".join([self.frame_header, self.frame_address, self.protocol_header, payload_hex])
        )
        return self.packet

    def parse_packet(self, packet):
        """
        Parse a header and payload from a packet.
        packet: bytes:
        """
        if packet is None:
            return (None, "packet:none")
        header_len = 36
        if len(packet) < 36:
            return (None, "bytes:missing")

        # Parse the header and payload
        header_bytes = packet[:header_len]
        payload_bytes = packet[header_len:]

        # little endian
        # 0: size
        # 1: origin/tagged/addressable/protocol
        # 2: source
        # 3: target (mac address)
        # 4: reserved
        # 5: reserved
        # 6: ack_required/res_required
        # 7: sequence
        # 8: reserved
        # 9: type
        # 10: reserved
        header_vals = struct.unpack("<HHIQIHBBQHH", header_bytes)
        header = {}
        header["size"] = header_vals[0]
        header["source"] = header_vals[2]
        header["target"] = header_vals[3]
        header["sequence"] = header_vals[7]
        header["type"] = header_vals[9]

        if header["size"] != len(packet):
            return (None, "mismatch:size")
        else:
            return (header, payload_bytes)

    def set_msg_type(self, msg_type):
        """
        Set the message type
        """
        self.msg_type = msg_type
        self.msg_type_hex = MESSAGE_TYPES[msg_type]
