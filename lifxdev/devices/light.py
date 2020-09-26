#!/usr/bin/env python3

from typing import NamedTuple

from lifxdev.devices import device
from lifxdev.messages import light_messages
from lifxdev.messages import packet


class Hsbk(NamedTuple):
    """Human-readable HSBK tuple"""

    hue: float
    saturation: float
    brightness: float
    kelvin: int

    @classmethod
    def from_packet(cls, hsbk: packet.Hsbk) -> "Hsbk":
        """Create a HSBK tuple from a message packet"""
        max_hue = (1 << hsbk.get_type("hue").value[0]) - 1
        max_saturation = (1 << hsbk.get_type("saturation").value[0]) - 1
        max_brightness = (1 << hsbk.get_type("brightness").value[0]) - 1

        hue = 360 * hsbk["hue"] / max_hue
        saturation = hsbk["saturation"] / max_saturation
        brightness = hsbk["brightness"] / max_brightness
        kelvin = hsbk["kelvin"]

        return cls(hue=hue, saturation=saturation, brightness=brightness, kelvin=kelvin)

    def to_packet(self) -> packet.Hsbk:
        """Create a message packet from an HSBK tuple"""
        hsbk = packet.Hsbk()
        max_hue = (1 << hsbk.get_type("hue").value[0]) - 1
        max_saturation = (1 << hsbk.get_type("saturation").value[0]) - 1
        max_brightness = (1 << hsbk.get_type("brightness").value[0]) - 1

        hsbk["hue"] = self.hue * max_hue / 360
        hsbk["saturation"] = self.saturation * max_saturation
        hsbk["brightness"] = self.brightness * max_brightness
        hsbk["kelvin"] = self.kelvin
        return hsbk


class LifxLight(device.LifxDevice):
    def get_color(self) -> Hsbk:
        """Returns the HSBK of the device."""
        # TODO convert to human-readable color info
        response = self.send_recv(light_messages.Get(), res_required=True)
        return Hsbk.from_packet(response[0].payload["color"])

    def get_infrared(self) -> float:
        """Get the current infrared level with 1.0 being the maximum."""
        response = self.send_recv(light_messages.GetInfrared(), res_required=True)
        ir_state = response[0].payload
        size = ir_state.get_type("brightness").value[0]
        return ir_state["brightness"] / ((1 << size) - 1)

    def get_power(self) -> bool:
        """Return True if the light is powered on."""
        response = self.send_recv(light_messages.GetPower(), res_required=True)
        return response[0].payload["level"]
