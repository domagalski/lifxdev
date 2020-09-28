#!/usr/bin/env python3

from typing import NamedTuple, Union, Tuple

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

    @classmethod
    def from_tuple(cls, hsbk: Union[Tuple, "Hsbk"]) -> "Hsbk":
        """Create a HSBK tuple from a normal tuple. Assume input is human-readable"""
        if isinstance(hsbk, type(cls)):
            return hsbk
        hue, saturation, brightness, kelvin = hsbk
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


class Rgb(NamedTuple):
    """RGB with normalization"""

    norm: float
    red: float
    green: float
    blue: float


def rgba2hsbk(rgb: Rgb, kelvin: int) -> Hsbk:
    """
    Convert RGBA to HSBK.

    kelvin mainly sets white balance for photography.
    """
    red = rgb.red
    green = rgb.green
    blue = rgb.blue
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
    brightness = max_col / rgb.norm

    return Hsbk(hue=hue, saturation=sat, brightness=brightness, kelvin=kelvin)
