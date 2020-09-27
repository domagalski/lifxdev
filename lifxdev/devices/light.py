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


class Rgba(NamedTuple):
    # TODO normalization depends on matplotlib conventions
    """RGBA with max value as 1.0"""
    norm: float
    red: float
    green: float
    blue: float
    alpha: float = None


class LifxLight(device.LifxDevice):
    """Light control"""

    def get_color(self) -> Hsbk:
        """Get the color of the device

        Returns:
            The human-readable HSBK of the light.
        """
        response = self.send_recv(light_messages.Get(), res_required=True)
        return Hsbk.from_packet(response[0].payload["color"])

    def get_power(self) -> bool:
        """Get the power state of the light.

        Returns:
            True if the light is powered on. False if off.
        """
        response = self.send_recv(light_messages.GetPower(), res_required=True)
        return response[0].payload["level"]

    def set_color(
        self,
        hsbk: Hsbk,
        duration_s: float,
        *,
        ack_required: bool = True,
    ) -> Optional[packet.LifxResponse]:
        """Set the color of the light.

        Args:
            hsbk: (Hsbk) Human-readable HSBK tuple.
            duration_s: (float) The time in seconds to make the color transition.
            ack_required: (bool) True gets an acknowledgement from the light.

        Returns:
            If ack_required, then get a color tuple as a response, else None.
        """
        set_color_msg = light_messages.SetColor(
            color=hsbk.to_packet(),
            duration=int(duration_s * 1000),
        )
        return self.send_msg(set_color_msg, ack_required=ack_required)

    def set_power(
        self,
        state: bool,
        duration_s: float,
        *,
        ack_required: bool = True,
    ) -> Optional[packet.LifxResponse]:
        """Set power state on the bulb.

        Args:
            state: (bool) True powers on the light. False powers it off.
            duration_s: (float) The time in seconds to make the color transition.
            ack_required: (bool) True gets an acknowledgement from the light.

        Returns:
            If ack_required, get an acknowledgement LIFX response tuple.
        """
        power = light_messages.SetPower(level=state, duration=int(duration_s * 1000))
        return self.send_msg(power, ack_required=ack_required)


class LifxInfraredLight(LifxLight):
    """Light with IR control"""

    def get_infrared(self) -> float:
        """Get the current infrared level with 1.0 being the maximum."""
        response = self.send_recv(light_messages.GetInfrared(), res_required=True)
        ir_state = response[0].payload
        return ir_state["brightness"] / ir_state.get_max("brightness")

    def set_infrared(
        self, brightness: float, *, ack_required: bool = True
    ) -> Optional[packet.LifxResponse]:
        """Set the infrared level on the bulb.

        Args:
            brightness: (float) IR brightness level. 1.0 is the maximum.
            ack_required: (bool) True gets an acknowledgement from the light.

        Returns:
            If ack_required, then return the IR level response.
        """
        ir = light_messages.SetInfrared()
        max_brightness = ir.get_max("brightness")
        ir["brightness"] = int(brightness * max_brightness)
        return self.send_msg(ir, ack_required=ack_required)


def rgba2hsbk(rgba: Rgba, kelvin: int) -> Hsbk:
    """
    Convert RGBA to HSBK.

    Assume max(rgba) == 1

    kelvin mainly sets white balance for photography.
    """
    red = rgba.red
    green = rgba.green
    blue = rgba.blue
    max_col = max(red, green, blue)
    min_col = min(red, green, blue)

    # Get the hue
    hue = 0
    h_scale = 60.0
    if max_col == min_col:
        hue = 0.0
    elif max_col == red:
        hue = h_scale * ((green - blue) / (max_col - min_col))
    elif max_col == green:
        hue = h_scale * (2 + (blue - red) / (max_col - min_col))
    elif max_col == blue:
        hue = h_scale * (4 + (red - green) / (max_col - min_col))

    # Fix wrapping for hue
    while hue > 360:
        hue -= 360
    while hue < 0:
        hue += 360

    # get the saturation
    sat = 0.0
    if max_col:
        sat = (max_col - min_col) / max_col

    # brightness
    brightness = max_col / rgba.norm

    return Hsbk(hue=hue, saturation=sat, brightness=brightness, kelvin=kelvin)
