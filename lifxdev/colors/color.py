#!/usr/bin/env python3

import dataclasses
import random
from typing import Union

import numpy as np
from matplotlib import colormaps
from matplotlib import colors

from lifxdev.messages import packet

KELVIN = 5500


@dataclasses.dataclass
class Hsbk:
    """Human-readable HSBK tuple"""

    hue: float
    saturation: float
    brightness: float
    kelvin: int

    @classmethod
    def from_packet(cls, hsbk: packet.Hsbk) -> "Hsbk":
        """Create a HSBK tuple from a message packet"""
        max_hue = hsbk.get_max("hue") + 1
        max_saturation = hsbk.get_max("saturation")
        max_brightness = hsbk.get_max("brightness")

        hue = 360 * hsbk["hue"] / max_hue
        saturation = hsbk["saturation"] / max_saturation
        brightness = hsbk["brightness"] / max_brightness
        kelvin = hsbk["kelvin"]

        return cls(hue=hue, saturation=saturation, brightness=brightness, kelvin=kelvin)

    @classmethod
    def from_tuple(cls, hsbk: Union[tuple, "Hsbk"]) -> "Hsbk":
        """Create a HSBK tuple from a normal tuple. Assume input is human-readable"""
        if isinstance(hsbk, Hsbk):
            return hsbk
        hue, saturation, brightness, kelvin = hsbk
        return cls(hue=hue, saturation=saturation, brightness=brightness, kelvin=kelvin)

    def max_brightness(self, brightness: float) -> "Hsbk":
        """Force the brightness to be at most a specific value"""
        if self.brightness > brightness:
            return dataclasses.replace(self, brightness=brightness)
        return self

    def to_packet(self) -> packet.Hsbk:
        """Create a message packet from an HSBK tuple"""
        hsbk = packet.Hsbk()
        max_hue = hsbk.get_max("hue") + 1
        max_saturation = hsbk.get_max("saturation")
        max_brightness = hsbk.get_max("brightness")

        hsbk["hue"] = int(self.hue * max_hue / 360) % max_hue
        hsbk["saturation"] = min(int(self.saturation * max_saturation), max_saturation)
        hsbk["brightness"] = min(int(self.brightness * max_brightness), max_brightness)
        hsbk["kelvin"] = int(self.kelvin)
        return hsbk


def get_colormap(
    cmap: str | colors.Colormap,
    length: int,
    kelvin: int = KELVIN,
    *,
    randomize: bool = False,
) -> list[Hsbk]:
    """Get a colormap as HSBK values

    Args:
        cmap: A matplotlib colormap name or object get HSBK colors from.
        length: The number of colors to return in the list.
        kelvin: Color temperature of white colors in the colormap.
        randomize: Shuffle the ordering of the colors.

    Returns:
        A list of HSBK values for the colormap.
    """
    mpl_cmap = colormaps.get_cmap(cmap) if isinstance(cmap, str) else cmap

    if length < 1:
        raise ValueError("length must be at least one.")
    elif length == 1:
        selectors = [random.random() if randomize else 0.0]
    else:
        selectors = [ii / (length - 1) for ii in range(length)]
    if randomize:
        offset = random.random()
        selectors = [(idx + offset) % 1.0 for idx in selectors]
        random.shuffle(selectors)

    rgb_array = np.array(colors.to_rgba_array(mpl_cmap(selectors))).transpose()[:3].transpose()
    hsv_array = colors.rgb_to_hsv(rgb_array)
    hsbk_list = [Hsbk.from_tuple((360 * hsv[0],) + tuple(hsv[1:]) + (kelvin,)) for hsv in hsv_array]
    return hsbk_list


def get_all_colormaps() -> list[str]:
    """Get a list of all colormaps"""
    return sorted(colormaps.keys())
