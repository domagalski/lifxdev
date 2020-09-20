#!/usr/bin/env pythom3


"""Light messages

https://lan.developer.lifx.com/docs/light-messages
"""

from lifxdev.payload import packet


@packet.set_message_type(101, is_response=True)
class Get(packet.LifxMessage):
    pass


@packet.set_message_type(102)
class SetColor(packet.LifxMessage):
    registers: packet.REGISTER_T = [
        ("reserved", packet.LifxType.u8, 1),
        ("color", packet.Hsbk(), 1),
        ("duration", packet.LifxType.u32, 1),
    ]


@packet.set_message_type(103)
class SetWaveform(packet.LifxMessage):
    registers: packet.REGISTER_T = [
        ("reserved", packet.LifxType.u8, 1),
        ("transient", packet.LifxType.u8, 1),
        ("color", packet.Hsbk(), 1),
        ("period", packet.LifxType.u32, 1),
        ("cycles", packet.LifxType.f32, 1),
        ("skew_ratio", packet.LifxType.s16, 1),
        ("waveform", packet.LifxType.u8, 1),
    ]
