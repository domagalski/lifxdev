#!/usr/bin/env python3

import logging
import unittest

from lifxdev.messages import packet
from lifxdev.messages import light_messages


class PacketTest(unittest.TestCase):
    def test_hsbk(self):
        hsbk = packet.Hsbk()
        hsbk["hue"] = 0
        hsbk["saturation"] = 65535
        hsbk["brightness"] = 65535
        hsbk["kelvin"] = 5500

        hsbk_bytes = hsbk.to_bytes()
        bytes_ints = [int(b) for b in hsbk_bytes]
        self.assertEqual(bytes_ints, [0, 0, 255, 255, 255, 255, 124, 21])

        hsbk_from_bytes = packet.Hsbk.from_bytes(hsbk_bytes)
        self.assertEqual(hsbk_from_bytes["hue"], hsbk["hue"])
        self.assertEqual(hsbk_from_bytes["saturation"], hsbk["saturation"])
        self.assertEqual(hsbk_from_bytes["brightness"], hsbk["brightness"])
        self.assertEqual(hsbk_from_bytes["kelvin"], hsbk["kelvin"])

    def test_frame(self):
        """Generate a frame based on the LIFX green light example"""
        lifx_ref = bytes([0x31, 0x0, 0x0, 0x34, 0x0, 0x0, 0x0, 0x0])

        frame = packet.Frame()
        frame["tagged"] = True
        frame["size"] = 49

        frame_bytes = frame.to_bytes()
        self.assertEqual(frame_bytes, lifx_ref)
        self.assertEqual(len(frame), frame.len())
        self.assertEqual(len(frame), 8)
        self.assertEqual(len(frame_bytes), len(frame))

        frame_from_bytes = packet.Frame.from_bytes(frame_bytes)
        self.assertEqual(frame_from_bytes["size"], frame["size"])
        self.assertEqual(frame_from_bytes["tagged"], frame["tagged"])

    def test_frame_address(self):
        """Green light example doesn't have anything here. Just measure the size."""
        frame_address = packet.FrameAddress()
        frame_address["target"] = "01:23:45:67:89:ab"
        frame_address["ack_required"] = True
        frame_address["res_required"] = True
        frame_address["sequence"] = 127
        frame_address_bytes = frame_address.to_bytes()
        self.assertEqual(len(frame_address), frame_address.len())
        self.assertEqual(len(frame_address), 16)
        self.assertEqual(len(frame_address_bytes), len(frame_address))

        fa_from_bytes = packet.FrameAddress.from_bytes(frame_address_bytes)
        self.assertEqual(fa_from_bytes["target"], frame_address["target"])
        self.assertTrue(fa_from_bytes["res_required"])
        self.assertTrue(fa_from_bytes["ack_required"])
        self.assertEqual(fa_from_bytes["res_required"], frame_address["res_required"])
        self.assertEqual(fa_from_bytes["ack_required"], frame_address["ack_required"])
        self.assertEqual(fa_from_bytes["sequence"], frame_address["sequence"])

    def test_protocol_header(self):
        """Generate a protocol header based on the LIFX green light example."""
        lifx_ref = bytes([0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x66, 0x0, 0x0, 0x0])

        protocol_header = packet.ProtocolHeader()
        protocol_header["type"] = light_messages.SetColor.type

        # Encode the message.
        message_bytes = protocol_header.to_bytes()
        self.assertEqual(message_bytes, lifx_ref)
        self.assertEqual(len(protocol_header), protocol_header.len())
        self.assertEqual(len(protocol_header), 12)
        self.assertEqual(len(message_bytes), len(protocol_header))

        # Decode from bytes
        ph_from_bytes = packet.ProtocolHeader.from_bytes(message_bytes)
        self.assertEqual(ph_from_bytes["type"], light_messages.SetColor.type)

    def test_packet(self):
        lifx_packet = packet.PacketComm()
        hsbk = packet.Hsbk(hue=21845, saturation=65535, brightness=65535, kelvin=3500)
        green = light_messages.SetColor(color=hsbk, duration=1024)

        payload_bytes, _ = lifx_packet.get_bytes_and_source(
            payload=green,
            mac_addr="00:00:00:00:00:00",
            res_required=False,
            ack_required=False,
            sequence=0,
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
