#!/usr/bin/env python3

import collections
import enum
import logging
import os
import socket
import struct
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple, Type, Union

from lifxdev.util import util

LIFX_PORT = 56700
REGISTER_T = List[Tuple[str, Optional[int], str]]


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

    def __str__(self) -> str:
        segments = [f"{nn}={self.get_value(nn)}" for nn in self._names]
        join = "\n".join(segments)
        return f"{join}"

    def __repr__(self) -> str:
        return f"<{type(self).__name__}({id(self)})>\n{self.__str__()}"

    def __eq__(self, other: "LifxStruct") -> bool:
        if type(self) != type(other):
            return False

        for name in self._names:
            value_self = self.get_value(name)
            value_other = other.get_value(name)
            if value_self != value_other:
                return False
        return True

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

    def __getitem__(self, name: str) -> Union[int, List[int]]:
        return self.get_value(name)

    def get_value(self, name: str) -> Union[int, List[int]]:
        """Get a register value by name.

        Returns:
            A single value if the register length is 1 else return the array of values.
        """
        name = name.lower()
        if name not in self._names:
            raise KeyError(f"{name!r} not a valid register name")

        value = self._values[name]
        if len(value) == 1:
            value = value[0]
        return value

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

        # Force reserved registers to be null
        if "reserved" in name:
            value = [0] * self.get_array_size(name)
            idx = None

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
            self._values[name] = value
        else:
            self._values[name][idx] = value

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
        size = self.get_value("size")
        source = self.get_value("source")

        bit_field = self.get_value("protocol")
        offset = self.get_nbits_per_name("protocol")
        bit_field |= self.get_value("addressable") << offset
        offset += self.get_nbits_per_name("addressable")
        bit_field |= self.get_value("tagged") << offset
        offset += self.get_nbits_per_name("tagged")
        bit_field |= self.get_value("origin") << offset

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
        if name == "target":
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
        sequence_bytes = struct.pack(self._fmt("sequence"), self.get_value("sequence"))

        bit_field = int(self.get_value("res_required"))
        offset = self.get_nbits_per_name("res_required")
        bit_field |= int(self.get_value("ack_required")) << offset
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
        (bit_field,) = struct.unpack("<B", bit_field_bytes)
        frame_address["res_required"] = bool(bit_field % 2)
        frame_address["ack_required"] = bool(bit_field // 2)

        return frame_address


class ProtocolHeader(LifxStruct):
    registers: REGISTER_T = [
        ("reserved_1", LifxType.u64, 1),
        ("type", LifxType.u16, 1),
        ("reserved_2", LifxType.u16, 1),
    ]


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
    """LIFX struct used as a message type payload."""

    # integer identifier of for the protocol header of LIFX packets.
    name: Optional[str] = None
    type: Optional[int] = None

    def __repr__(self) -> str:
        super_str = super().__str__()
        msg_str = f"<{self.name}({self.type}): {id(self)}>"
        if super_str:
            msg_str = f"{msg_str}\n{super_str}"
        return msg_str

    def __str__(self) -> str:
        super_str = super().__str__()
        msg_str = f"<{self.name}({self.type})>"
        if super_str:
            msg_str = f"{msg_str}\n{super_str}"
        return msg_str


class LifxResponse(NamedTuple):
    frame: Frame
    frame_address: FrameAddress
    protocol_header: ProtocolHeader
    payload: LifxMessage

    def __str__(self) -> str:
        return "\n".join(
            [
                "LifxResponse.frame:",
                str(self.frame),
                "---",
                "LifxResponse.frame_address:",
                str(self.frame_address),
                "---",
                "LifxResponse.protocol_header:",
                str(self.protocol_header),
                "---",
                str(self.payload),
            ]
        )


# Used for parsing responses from LIFX bulbs
# This maps the protocol header type to a LifxMessage class to generate using bytes
_MESSAGE_TYPES: Dict[int, Type] = {}


def set_message_type(message_type: int) -> Callable:
    """Create a LifxMessage class with the message type auto-set.

    Args:
        message_type: (int) LIFX message type for the protocol header
    """

    def _msg_type_decorator(cls: Type) -> Type:
        class _LifxMessage(cls):
            pass

        _LifxMessage.name = cls.__name__
        _LifxMessage.type = message_type
        _MESSAGE_TYPES[message_type] = _LifxMessage
        return _LifxMessage

    return _msg_type_decorator


@set_message_type(45)
class Acknowledgement(LifxMessage):
    """Acknowledgement message

    Defined here: https://lan.developer.lifx.com/docs/device-messages
    This is the message type returned when ack_required=True in the frame address.
    """

    pass


#
# Socket communication
#


class UdpSender(NamedTuple):
    """Send messages to a single IP/port"""

    # IP address of the LIFX device.
    ip: str

    # UDP socket for communication
    comm: socket.socket

    # UDP port on the LIFX device
    port: int = LIFX_PORT

    # Mac address of the LIFX device
    mac_addr: Optional[str] = None


class PacketComm:
    """Communicate packets with LIFX devices"""

    # TODO determine the minimum buffer size for recieving messages
    def __init__(self, comm: UdpSender, buffer_size: int = 4096, verbose: bool = False):
        """Create a packet communicator

        Args:
            comm (socket): pre-configured UDP socket
            buffer_size:
        """
        self._buffer_size = buffer_size
        self._comm = comm
        self._log_func = logging.info if verbose else logging.debug

    @staticmethod
    def decode_bytes(
        message_bytes: bytes,
        nominal_source: Optional[int] = None,
        nominal_sequence: Optional[int] = None,
    ) -> LifxResponse:
        def _get_nbytes(cls: Type) -> int:
            n_bits = 0
            for _, rtype, rlen in cls.registers:
                n_bits += rtype.value[0] * rlen
            return n_bits // 8

        # Decode the Frame information
        chunk_len = _get_nbytes(Frame)
        frame = Frame.from_bytes(message_bytes[:chunk_len])

        # Verify the message size matches the expected size
        size = frame["size"]
        if len(message_bytes) != size:
            raise RuntimeError(f"Message size mismatch: R({len(message_bytes)}) != E({size})")

        # Verify the source is the expected source
        if nominal_source is not None:
            source = frame["source"]
            if source != nominal_source:
                raise RuntimeError(f"Source mismatch: R({source}) != E({nominal_source})")

        # Decode the Frame Address
        offset = chunk_len
        chunk_len = _get_nbytes(FrameAddress)
        frame_address = FrameAddress.from_bytes(message_bytes[offset : offset + chunk_len])

        # Verify the sequence is the expected sequence
        if nominal_sequence is not None:
            sequence = frame_address["sequence"]
            if sequence != nominal_sequence:
                raise RuntimeError(f"Sequence mismatch: R({sequence}) != E({nominal_sequence})")

        # Decode the payload
        offset += chunk_len
        chunk_len = _get_nbytes(ProtocolHeader)
        protocol_header = ProtocolHeader.from_bytes(message_bytes[offset : offset + chunk_len])

        offset += chunk_len
        payload_klass = _MESSAGE_TYPES[protocol_header["type"]]
        chunk_len = _get_nbytes(payload_klass)
        payload = payload_klass.from_bytes(message_bytes[offset : offset + chunk_len])

        return LifxResponse(
            frame=frame,
            frame_address=frame_address,
            protocol_header=protocol_header,
            payload=payload,
        )

    @staticmethod
    def get_bytes_and_source(
        *,
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
        if mac_addr:
            frame_address["target"] = mac_addr
        frame_address["res_required"] = res_required
        frame_address["ack_required"] = ack_required
        frame_address["sequence"] = sequence

        # Protocol header only requires setting the type.
        if not payload.type:
            raise ValueError("Payload has no message type.")
        protocol_header["type"] = payload.type

        # Generate the frame
        # tagged must be true when sending a GetService message
        frame["tagged"] = bool(mac_addr) or payload.type == 2
        frame["source"] = os.getpid() if source is None else source
        frame["size"] = len(frame) + len(frame_address) + len(protocol_header) + len(payload)

        # Generate the bytes for the packet
        packet_bytes = frame.to_bytes()
        packet_bytes += frame_address.to_bytes()
        packet_bytes += protocol_header.to_bytes()
        packet_bytes += payload.to_bytes()

        return packet_bytes, frame["source"]

    def send_recv(self, verbose: bool = False, **kwargs) -> Optional[LifxResponse]:
        """Send a packet to a LIFX device and get a response"""
        log_func = logging.info if verbose else self._log_func
        addr = (self._comm.ip, self._comm.port)
        comm = self._comm.comm

        kwargs["mac_addr"] = self._comm.mac_addr
        packet_bytes, source = self.get_bytes_and_source(**kwargs)

        payload_name = kwargs["payload"].name
        log_func(f"Sending {payload_name} message to {addr[0]}:{addr[1]}")
        comm.sendto(packet_bytes, addr)

        # TODO handle calls where multiple responses are expected.
        if kwargs.get("ack_required", False) or kwargs.get("res_required", False):
            recv_bytes, recv_addr = comm.recvfrom(self._buffer_size)
            response = self.decode_bytes(recv_bytes, source, kwargs.get("sequence", 0))
            payload_name = response.payload.name
            log_func(f"Received {payload_name} message from {recv_addr[0]}:{recv_addr[1]}")
            return response
