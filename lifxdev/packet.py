#!/usr/bin/env python3

import collections
import enum
import os
from typing import List, Optional, Tuple, Type, Union

import numpy as np

from lifxdev import util

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


class ResponseType(enum.Enum):
    StateService = 3
    StateHostInfo = 13
    StateHostFirmware = 15
    StateWifiInfo = 17
    StateWifiFirmware = 19
    StatePowerDevice = 22
    StateLabel = 25
    StateVersion = 33
    StateInfo = 33
    StateLocation = 50
    StateGroup = 53
    State = 107
    StatePowerLight = 118
    StateExtendedColorZones = 512
    StateDeviceChain = 702
    StateTileState64 = 711


class LifxType(enum.Enum):
    """Type definition:

    0: (bool) signed
    1: (int) size in bits
    2: (type) python type
    """

    bool = (False, 1, bool)
    char = (False, 8, ord)
    f32 = (True, 32, float)
    s16 = (True, 16, int)
    u2 = (False, 2, int)  # 8 bit int where only 2 bits are used
    u6 = (False, 6, int)  # 8 bit int where only 6 bits are used
    u8 = (False, 8, int)
    u12 = (False, 12, int)  # 16 bit int where only 12 bits are used
    u16 = (False, 16, int)
    u32 = (False, 32, int)
    u64 = (False, 64, int)


class LifxStruct:
    """Packed structure for generating byte representations of LIFX bit tables.

    LIFX packets are little endian.

    Register definition:
        0: (str) name
        1: (enum) type, if a LifxStruct subclass, use the type instead of a str
        2: (int) number of items of the type
    """

    registers: List[Tuple[str, Optional[int], Union[str, Type]]] = []

    def __init__(self, **kwargs):
        # Set to tuples because they're immutable. _names and _sizes should not be changed.
        self._names: Tuple[str, ...] = tuple([rr[0].lower() for rr in self.registers])

        self._types = collections.OrderedDict()
        self._sizes = collections.OrderedDict()
        self._lens = collections.OrderedDict()
        self._values = collections.OrderedDict()
        for name, rr in zip(self._names, self.registers):
            self._types[name] = rr[1]
            self._sizes[name] = rr[1].value[1] * rr[2]
            self._lens[name] = rr[2]
            if isinstance(self._types[name], LifxType):
                default = [0] * self._lens[name]
            else:
                default = [self._types[name]] * self._lens[name]
            self._values[name] = default
            self.set_value(name, kwargs.get(name, default))

    def get_size_bits(self) -> int:
        """Get the size in bits of an individual LifxStruct object"""
        return sum(self._sizes.values())

    def get_size_bytes(self) -> int:
        """Return the number of bytes in the LifxStruct"""
        return self.get_size_bits() // 8

    def get_array_size(self, name: str) -> int:
        name = name.lower()
        return self._lens[name]

    @property
    def value(self) -> Tuple[bool, int, None]:
        """Mimic the value attribute of the LifxType enum"""
        return (False, self.get_size_bits(), None)

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

    def to_bytes(self, *, as_ints: bool = False) -> Union[bytes, List[int]]:
        """Convert the LifxStruct to its bytes representation

        Args:
            as_ints: (bool) Return the list of ints representing the bytes.
        """
        assert len(self._names) == len(self._values)
        assert len(self._types) == len(self._values)
        assert len(self._sizes) == len(self._values)
        assert len(self._lens) == len(self._values)

        # Bit offsets are used for setting bits in the numerical representation.
        # Numpy does some funky stuff with types, so numbers needed to be converted
        # back to native Python integers
        sizes = list(self._sizes.values())
        offsets = [int(n) for n in np.r_[0, np.cumsum(sizes)[:-1]]]
        number = 0
        for name, size in zip(self._values, offsets):
            n_bits = self._types[name].value[1]
            value_list = self._values[name]
            if issubclass(type(self._types[name]), LifxStruct):
                for ii, value in enumerate(value_list):
                    for jj, nn in enumerate(value.to_bytes(as_ints=True)):
                        offset = size + ii * n_bits + jj * 8
                        number |= nn << offset
            else:
                for ii, value in enumerate(value_list):
                    offset = size + ii * n_bits
                    number |= value << offset

        # Get each byte from the integer representation
        bytes_list: List[int] = []
        for _ in range(len(self)):
            bytes_list.append(number % (1 << 8))
            number = number >> 8

        if as_ints:
            return bytes_list
        else:
            return bytes(bytes_list)


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


class LifxPacket(object):
    """Generic LIFX packet implementation"""

    def __init__(self):
        pass

    def generate_packet(
        self,
        message_type: Union[str, MessageType],
        mac_addr: Optional[Union[str, int]] = None,
        res_required: bool = False,
        ack_required: bool = False,
        sequence: int = 0,
        payload: Optional[LifxStruct] = None,
    ) -> bytes:
        """Generate a LIFX packet.

        Args:
            msg_type: (MessageType) Type of the message from MESSAGE_TYPES
            mac_addr: (str) MAC address of the target bulb.
            res_required: (bool) Require a response from the light.
            ack_required: (bool) Require an acknowledgement from the light.
            sequence: (int) Optional identifier to label packets.
            payload: (LifxStruct): Optional payload LifxStruct.
        """
        # frame = Frame(tagged=True, size=49)
        frame = Frame()
        frame_address = FrameAddress()
        protocol_header = ProtocolHeader()

        # Set the frame address fields
        frame_address["target"] = mac_addr
        frame_address["res_required"] = res_required
        frame_address["ack_required"] = ack_required
        frame_address["sequence"] = sequence

        # Protocol header only requires setting the type.
        protocol_header["type"] = message_type

        # Generate the frame
        frame["tagged"] = bool(mac_addr)
        frame["source"] = os.getpid()
        frame["size"] = len(frame) + len(frame_address) + len(protocol_header)
        if payload:
            frame["size"] += len(payload)

        # Generate the bytes for the packet
        packet_bytes = frame.to_bytes() + frame_address.to_bytes() + protocol_header.to_bytes()
        if payload():
            packet_bytes += payload.to_bytes()

        return packet_bytes
