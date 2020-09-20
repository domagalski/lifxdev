#!/usr/bin/env python3

import logging
import unittest

from lifxdev import packet
from lifxdev import payload


class PacketTest(unittest.TestCase):
    def test_frame(self):
        """Generate a frame based on the LIFX green light example"""
        lifx_ref = bytes([0x31, 0x0, 0x0, 0x34, 0x0, 0x0, 0x0, 0x0])

        frame = packet.Frame()
        frame["tagged"] = True
        frame["size"] = 49

        self.assertEqual(frame.to_bytes(), lifx_ref)
        self.assertEqual(len(frame), frame.len())
        self.assertEqual(len(frame), 8)
        self.assertEqual(len(frame.to_bytes()), len(frame))

    def test_frame_address(self):
        """Green light example doesn't have anything here. Just measure the size."""
        frame_address = packet.FrameAddress()
        frame_address["target"] = "00:00:00:00:00:00"
        self.assertEqual(len(frame_address), frame_address.len())
        self.assertEqual(len(frame_address), 16)
        self.assertEqual(len(frame_address.to_bytes()), len(frame_address))

    def test_protocol_header(self):
        """Generate a protocol header based on the LIFX green light example."""
        lifx_ref = bytes([0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x66, 0x0, 0x0, 0x0])

        protocol_header = packet.ProtocolHeader()
        protocol_header["type"] = packet.MessageType.SetColor

        self.assertEqual(protocol_header.to_bytes(), lifx_ref)
        self.assertEqual(len(protocol_header), protocol_header.len())
        self.assertEqual(len(protocol_header), 12)
        self.assertEqual(len(protocol_header.to_bytes()), len(protocol_header))

    def test_packet(self):
        lifx_packet = packet.LifxPacket()
        hsbk = payload.Hsbk(hue=21845, saturation=65535, brightness=65535, kelvin=3500)
        green = payload.SetColor(color=hsbk, duration=1024)

        payload_bytes, _ = lifx_packet.generate_packet(
            message_type=packet.MessageType.SetColor,
            mac_addr="00:00:00:00:00:00",
            res_required=False,
            ack_required=False,
            sequence=0,
            payload=green,
            source=0,
        )

        # Taken from the green light example
        lifx_ref = [
            0x31,
            0x00,
            0x00,
            0x34,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x66,
            0x00,
            0x00,
            0x00,
            0x00,
            0x55,
            0x55,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xAC,
            0x0D,
            0x00,
            0x04,
            0x00,
            0x00,
        ]
        payload_bytes = [int(bb) for bb in payload_bytes]
        self.assertEqual(payload_bytes, lifx_ref)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    unittest.main()
