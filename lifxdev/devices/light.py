#!/usr/bin/env python3

from typing import NamedTuple, Optional

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
        max_hue = hsbk.get_max("hue")
        max_saturation = hsbk.get_max("saturation")
        max_brightness = hsbk.get_max("brightness")

        hue = 360 * hsbk["hue"] / max_hue
        saturation = hsbk["saturation"] / max_saturation
        brightness = hsbk["brightness"] / max_brightness
        kelvin = hsbk["kelvin"]

        return cls(hue=hue, saturation=saturation, brightness=brightness, kelvin=kelvin)

    def to_packet(self) -> packet.Hsbk:
        """Create a message packet from an HSBK tuple"""
        hsbk = packet.Hsbk()
        max_hue = hsbk.get_max("hue")
        max_saturation = hsbk.get_max("saturation")
        max_brightness = hsbk.get_max("brightness")

        hsbk["hue"] = int(self.hue * max_hue / 360) % max_hue
        hsbk["saturation"] = min(int(self.saturation * max_saturation), max_saturation)
        hsbk["brightness"] = min(int(self.brightness * max_brightness), max_brightness)
        hsbk["kelvin"] = int(self.kelvin)
        return hsbk


class LifxLight(device.LifxDevice):
    def get_color(self) -> Hsbk:
        """Returns the HSBK of the device."""
        response = self.send_recv(light_messages.Get(), res_required=True)
        return Hsbk.from_packet(response[0].payload["color"])

    def get_infrared(self) -> float:
        """Get the current infrared level with 1.0 being the maximum."""
        response = self.send_recv(light_messages.GetInfrared(), res_required=True)
        ir_state = response[0].payload
        return ir_state["brightness"] / ir_state.get_max("brightness")

    def get_power(self) -> bool:
        """Return True if the light is powered on."""
        response = self.send_recv(light_messages.GetPower(), res_required=True)
        return response[0].payload["level"]

    def set_color(
        self, hsbk: Hsbk, duration_s: float, *, ack_required: bool = True
    ) -> Optional[Hsbk]:
        """Set the color according to a human-readable HSBK tuple"""
        set_color_msg = light_messages.SetColor(
            color=hsbk.to_packet(), duration=int(duration_s * 1e3)
        )
        if self.send_recv(set_color_msg, ack_required=ack_required):
            return self.get_color()

    def set_infrared(self, brightness: float, *, ack_required: bool = True) -> Optional[float]:
        ir = light_messages.SetInfrared()
        max_brightness = ir.get_max("brightness")
        ir["brightness"] = int(brightness * max_brightness)
        if self.send_recv(ir, ack_required=ack_required):
            return self.get_infrared()

    # def set_power(self, state: bool, duration_s: float, *, ack_required: bool = True):
    #    """
