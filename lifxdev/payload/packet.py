#!/usr/bin/env python3

import collections
import enum
import os
import struct
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple, Type, Union

from lifxdev.util import util

REGISTER_T = List[Tuple[str, Optional[int], str]]


class MessageType(enum.Enum):
    # Device messages
    GetService = 2
    GetHostInfo = 12
    GetHostFirmware = 14
    GetWifiInfo = 16
    GetWifiFirmware = 18
    GetPowerDevice = 20
    SetPowerDevice = 21
    GetLabel = 23
    SetLabel = 24
    GetVersion = 32
    GetInfo = 32
    Acknowledgement = 45
    GetLocation = 48
    SetLocation = 49
    GetGroup = 51
    SetGroup = 52
    EchoRequest = 58
    EchoResponse = 59
    # Light messages
    Get = 101
    SetColor = 102
    SetWaveform = 103
    SetWaveformOptional = 119
    GetPowerLight = 116
    SetPowerLight = 117
    # MultiZone (Z/Beam) messages
    SetExtendedColorZones = 510
    GetExtendedColorZones = 511
    # Tile messages
    GetDeviceChain = 701
    SetUserPosition = 703
    GetTileState64 = 707
    SetTileState64 = 715


class LifxType(enum.Enum):
    """Type definition:

    0: (int) size in bits
    1: (char) struct format (None if size % 8 > 0)
    """

    bool = (1, None)
    char = (8, "c")
    f32 = (32, "f")
    s16 = (16, "h")
    u2 = (2, None)  # 8 bit int where only 2 bits are used
    u6 = (6, None)  # 8 bit int where only 6 bits are used
    u8 = (8, "B")
    u12 = (12, None)  # 16 bit int where only 12 bits are used
    u16 = (16, "H")
    u32 = (32, "I")
    u64 = (64, "Q")


class LifxStruct:
    """Packed structure for generating byte representations of LIFX bit tables.

    LIFX packets are little endian.

    Register definition:
        0: (str) name
        1: (enum) type, if a LifxStruct subclass, use the type instead of a str
        2: (int) number of items of the type
    """

    registers: List[Tuple[str, Union[LifxType, "LifxStruct"], int]] = []

    def __init__(self, **kwargs):
        # Set to tuples because they're immutable. _names and _sizes should not be changed.
        self._names: Tuple[str, ...] = tuple([rr[0].lower() for rr in self.registers])

        self._types = collections.OrderedDict()
        self._sizes = collections.OrderedDict()
        self._lens = collections.OrderedDict()
        self._values = collections.OrderedDict()
        for name, rr in zip(self._names, self.registers):
            self._types[name] = rr[1]
            self._sizes[name] = rr[1].value[0] * rr[2]
            self._lens[name] = rr[2]
            if isinstance(self._types[name], LifxType):
                default = [0] * self._lens[name]
            else:
                default = [self._types[name]] * self._lens[name]
            self._values[name] = default
            self.set_value(name, kwargs.get(name, default))

    @classmethod
    def from_bytes(cls, message_bytes: bytes) -> "LifxStruct":
        """Create a LifxStruct from bytes

        Anything with irregular bits will have this class overrwitten.
        """
        decoded_registers = collections.defaultdict(list)

        offset = 0
        for reg_info in cls.registers:
            t_nbytes = 0
            rname, rtype, rlen = reg_info

            # Easy decoding using struct.unpack for LifxType data
            if isinstance(rtype, LifxType):
                if rtype.value[1] is None:
                    raise RuntimeError(f"Register {rname} cannot be represented as bytes.")

                t_nbytes = rtype.value[0] // 8 * rlen
                msg_chunk = message_bytes[offset : offset + t_nbytes]
                value_list = list(struct.unpack("<" + rtype.value[1] * rlen, msg_chunk))
                decoded_registers[rname] = value_list

            # If bytes are supposed to represent a type, use the from_bytes from that type
            else:
                t_nbytes = len(rtype) * rlen
                msg_chunk = message_bytes[offset : offset + t_nbytes]
                for _ in range(rlen):
                    decoded_registers[rname].append(rtype.from_bytes(msg_chunk[: len(rtype)]))
                    msg_chunk = msg_chunk[len(rtype) :]

            offset += t_nbytes

        return cls(**decoded_registers)

    def get_size_bits(self) -> int:
        """Get the size in bits of an individual LifxStruct object"""
        return sum(self._sizes.values())

    def get_size_bytes(self) -> int:
        """Return the number of bytes in the LifxStruct"""
        return self.get_size_bits() // 8

    def get_array_size(self, name: str) -> int:
        name = name.lower()
        return self._lens[name]

    def get_nbits_per_name(self, name: str) -> int:
        name = name.lower()
        return self._sizes[name]

    def get_nbytes_per_name(self, name: str) -> int:
        return self.get_nbits_per_name(name) // 8

    def get_type(self, name: str) -> Union[LifxType, "LifxStruct"]:
        name = name.lower()
        return self._types[name]

    @property
    def value(self) -> Tuple[int, None]:
        """Mimic the value attribute of the LifxType enum"""
        return (self.get_size_bits(), None)

    def __len__(self) -> int:
        return self.len()

    def len(self) -> int:
        """Return the number of bytes in the LifxStruct"""
        return self.get_size_bytes()

    def __getitem__(self, name: str) -> int:
        return self.get_value(name)

    def get_value(self, name: str) -> int:
        """Get a register value by name."""
        return self._values.get(name.lower(), 0)

    def __setitem__(self, name: str, value: int) -> None:
        self.set_value(name, value)

    def set_value(
        self,
        name: str,
        value: Union[int, "LifxStruct", List[int], List["LifxStruct"]],
        idx: Optional[int] = None,
    ) -> None:
        """Set a register value by name.

        Args:
            name: (str) name of the register to write
            value: Either a singular value or a list of values to write.
            idx: (int) if a single array item, the position in the array.
        """
        name = name.lower()
        if name not in self._names:
            raise KeyError(f"{name!r} not a valid register name")

        # Validate that if a list was passed, that it matches the register length
        n_items = self._lens[name]
        if isinstance(value, list):
            if len(value) != n_items:
                raise ValueError(
                    f"Value has length {len(value)}, "
                    f"but register {name} requires length {n_items}"
                )

        # Force the index to zero if a singular value has been passed in
        elif n_items == 1:
            idx = 0
        elif idx is None:
            raise ValueError("idx cannot be none for a singular value")

        # Set the value to the internal values dict
        if isinstance(value, list):
            self._values[name] = [self._check_value(name, vv) for vv in value]
        else:
            self._values[name][idx] = self._check_value(name, value)

    def _check_value(self, name: str, value: int) -> int:
        """Valudate that an integer value is within its bounds"""
        # Don't do an int check if the value is a LifxStruct type
        if not isinstance(self._types[name], LifxType):
            return value

        # TODO signed integers
        value = int(value)
        if value < 0 or value >= (1 << self._sizes[name]):
            raise ValueError(f"value {value} out of bounds for register {name!r}")
        return value

    def to_bytes(self) -> bytes:
        """Convert the LifxStruct to its bytes representation

        Args:
            as_ints: (bool) Return the list of ints representing the bytes.
        """
        assert len(self._names) == len(self._values)
        assert len(self._types) == len(self._values)
        assert len(self._sizes) == len(self._values)
        assert len(self._lens) == len(self._values)

        message_bytes = b""
        for reg_info in self.registers:
            rname, rtype, rlen = reg_info

            # Use struct.path for LifxTypes
            if isinstance(rtype, LifxType):
                if rtype.value[1] is None:
                    raise RuntimeError(f"Register {rname} cannot be represented as bytes.")
                fmt = "<" + rtype.value[1] * rlen
                message_bytes += struct.pack(fmt, *self._values[rname])

            # Use the LifxStruct to_bytes when not a LifxType
            else:
                for lstruct in self._values[rname]:
                    message_bytes += lstruct.to_bytes()

        return message_bytes


# Header description: https://lan.developer.lifx.com/docs/header-description


class Frame(LifxStruct):
    registers: REGISTER_T = [
        ("size", LifxType.u16, 1),
        ("protocol", LifxType.u12, 1),
        ("addressable", LifxType.bool, 1),
        ("tagged", LifxType.bool, 1),
        ("origin", LifxType.u2, 1),
        ("source", LifxType.u32, 1),
    ]

    def set_value(self, name: str, value: int) -> None:
        """LIFX Frame specification requires certain fields to be constant."""
        if name.lower() == "protocol":
            value = 1024
        elif name.lower() == "addressable":
            value = True
        elif name.lower() == "origin":
            value = 0
        super().set_value(name, value)

    def to_bytes(self) -> bytes:
        """Override defaults because of sub-byte packing"""
        size = self["size"][0]
        source = self["source"][0]

        bit_field = self.get_value("protocol")[0]
        offset = self.get_nbits_per_name("protocol")
        bit_field |= self.get_value("addressable")[0] << offset
        offset += self.get_nbits_per_name("addressable")
        bit_field |= self.get_value("tagged")[0] << offset
        offset += self.get_nbits_per_name("tagged")
        bit_field |= self.get_value("origin")[0] << offset

        return struct.pack("<HHI", size, bit_field, source)

    @classmethod
    def from_bytes(cls, message_bytes: bytes) -> "Frame":
        """Override defaults because of sub-byte packing"""
        size, bit_field, source = struct.unpack("<HHI", message_bytes)
        frame = cls(size=size, source=source)

        shift = frame.get_nbits_per_name("protocol")
        frame["protocol"] = bit_field % (1 << shift)
        bit_field = bit_field >> shift

        shift = frame.get_nbits_per_name("addressable")
        frame["addressable"] = bool(bit_field % (1 << shift))
        bit_field = bit_field >> shift

        shift = frame.get_nbits_per_name("tagged")
        frame["tagged"] = bool(bit_field % (1 << shift))
        bit_field = bit_field >> shift

        frame["origin"] = bit_field
        return frame


class FrameAddress(LifxStruct):
    registers: REGISTER_T = [
        ("target", LifxType.u8, 8),
        ("reserved_1", LifxType.u8, 6),
        ("res_required", LifxType.bool, 1),
        ("ack_required", LifxType.bool, 1),
        ("reserved_2", LifxType.u6, 1),
        ("sequence", LifxType.u8, 1),
    ]

    def set_value(self, name: str, value: int) -> None:
        """LIFX Frame Address specification requires certain fields to be constant.

        This also allows for the proper parsing of mac addresses.
        """
        name = name.lower()
        if "reserved" in name:
            value = [0] * self.get_array_size(name)
        elif name == "target":
            if isinstance(value, str):
                if util.is_str_mac(value):
                    value = util.mac_str_to_int_list(value)

        super().set_value(name, value)

    def _fmt(self, name: str) -> str:
        """Create a format string for a register name"""
        return "<" + self.get_type(name).value[1] * self.get_array_size(name)

    def to_bytes(self) -> bytes:
        """Override defaults because of sub-byte packing"""

        target_bytes = struct.pack(self._fmt("target"), *self.get_value("target"))
        res_1_bytes = struct.pack(self._fmt("reserved_1"), *self.get_value("reserved_1"))
        sequence_bytes = struct.pack(self._fmt("sequence"), *self.get_value("sequence"))

        bit_field = int(self.get_value("res_required")[0])
        offset = self.get_nbits_per_name("res_required")
        bit_field |= int(self.get_value("ack_required")[0]) << offset
        bit_field_bytes = struct.pack("<B", bit_field)

        return target_bytes + res_1_bytes + bit_field_bytes + sequence_bytes

    @classmethod
    def from_bytes(cls, message_bytes: bytes) -> "Frame":
        """Override defaults because of sub-byte packing"""
        frame_address = cls()
        get_len = frame_address.get_nbytes_per_name
        get_nbits = frame_address.get_nbits_per_name

        chunk_len = get_len("target")
        target_bytes = message_bytes[:chunk_len]
        offset = chunk_len + get_len("reserved_1")
        chunk_len = get_nbits("res_required") + get_nbits("ack_required") + get_nbits("reserved_2")
        chunk_len //= 8
        bit_field_bytes = message_bytes[offset : offset + chunk_len]
        offset += chunk_len

        chunk_len = get_len("sequence")
        sequence_bytes = message_bytes[offset : offset + chunk_len]

        frame_address["target"] = list(struct.unpack(frame_address._fmt("target"), target_bytes))
        frame_address["sequence"] = list(
            struct.unpack(frame_address._fmt("sequence"), sequence_bytes)
        )
        bit_field, = struct.unpack("<B", bit_field_bytes)
        frame_address["res_required"] = bool(bit_field % 2)
        frame_address["ack_required"] = bool(bit_field // 2)

        return frame_address


class ProtocolHeader(LifxStruct):
    registers: REGISTER_T = [
        ("reserved_1", LifxType.u64, 1),
        ("type", LifxType.u16, 1),
        ("reserved_2", LifxType.u16, 1),
    ]

    def set_value(self, name: str, value: int):
        """LIFX Protocol Address specification requires certain fields to be constant."""
        if "reserved" in name.lower():
            value = 0
        if name.lower() == "type":
            if isinstance(value, MessageType):
                value = value.value
            elif isinstance(value, str):
                value = MessageType[value].value

        super().set_value(name, value)


class Hsbk(LifxStruct):
    registers: REGISTER_T = [
        ("hue", LifxType.u16, 1),
        ("saturation", LifxType.u16, 1),
        ("brightness", LifxType.u16, 1),
        ("kelvin", LifxType.u16, 1),
    ]

    def set_value(self, name: str, value: Union[int, List[int]]):
        """Kelvin must be between 2500 and 9000."""
        if isinstance(value, list):
            if len(value) > 1:
                raise ValueError("HSBK value as list must be length 1")
            hsbk_value = value[0]
        else:
            hsbk_value = value

        # Only value check when setting a non-zero value.
        # Value checking on the zero would break the default constructor.
        if name.lower() == "kelvin" and hsbk_value:
            if hsbk_value < 2500 or hsbk_value > 9000:
                raise ValueError("Kelvin out of range.")

        super().set_value(name, hsbk_value)


#
# Handle payload messages and responses
#


class LifxMessage(LifxStruct):
    """LIFX struct that's meant as a payload."""

    # integer identifier of for the protocol header of LIFX packets.
    message_type: Optional[int] = None


class LifxResponse(NamedTuple):
    frame: Frame
    frame_address: FrameAddress
    protocol_header: ProtocolHeader
    payload: LifxMessage


_RESPONSE_CLASSES: Dict[int, Type] = {}


def set_message_type(message_type: int, *, is_response: bool = False):
    """Create a LifxMessage class with the message type auto-set.

    Args:
        message_type: (int) LIFX message type for the protocol header
        is_response: (int) Indicate that the message is a response type.
    """

    def _msg_type_decorator(cls: Type) -> Callable:
        class _LifxMessage(cls):
            pass

        _LifxMessage.message_type = message_type
        if is_response:
            _RESPONSE_CLASSES[message_type] = _LifxMessage

        return _LifxMessage

    return _msg_type_decorator


#
# Socket communication
#


class PacketComm:
    """Communicate packets with LIFX devices"""

    def __init__(self):
        pass

    def get_bytes_and_source(
        self,
        payload: LifxMessage,
        mac_addr: Optional[Union[str, int]] = None,
        res_required: bool = False,
        ack_required: bool = False,
        sequence: int = 0,
        source: Optional[int] = None,
    ) -> Tuple[bytes, int]:
        """Generate LIFX packet bytes.

        Args:
            mac_addr: (str) MAC address of the target bulb.
            res_required: (bool) Require a response from the light.
            ack_required: (bool) Require an acknowledgement from the light.
            sequence: (int) Optional identifier to label packets.
            payload: (LifxStruct): Optional payload LifxStruct.
            source: (int) Optional unique identifier to

        Returns:
            bytes and source identifier
        """
        frame = Frame()
        frame_address = FrameAddress()
        protocol_header = ProtocolHeader()

        # Set the frame address fields
        frame_address["target"] = mac_addr
        frame_address["res_required"] = res_required
        frame_address["ack_required"] = ack_required
        frame_address["sequence"] = sequence

        # Protocol header only requires setting the type.
        if not payload.message_type:
            raise ValueError("Payload has no message type.")
        protocol_header["type"] = payload.message_type

        # Generate the frame
        frame["tagged"] = bool(mac_addr)
        frame["source"] = os.getpid() if source is None else source
        frame["size"] = len(frame) + len(frame_address) + len(protocol_header) + len(payload)

        # Generate the bytes for the packet
        packet_bytes = frame.to_bytes()
        packet_bytes += frame_address.to_bytes()
        packet_bytes += protocol_header.to_bytes()
        packet_bytes += payload.to_bytes()

        return packet_bytes, frame["source"][0]
