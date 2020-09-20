#!/usr/bin/env python3

import re
import struct
from typing import List, Tuple, Union


def hsbk_human(hsbk: Union[Tuple, List]) -> Tuple:
    """Make hsbk human readable"""
    if not isinstance(hsbk, (tuple, list)):
        raise ValueError("hsbk must be a len 4 tuple/list")

    if not len(hsbk) == 4:
        raise ValueError("hsbk must have exactly 4 items.")

    hue, sat, brightness, kelvin = hsbk
    hue *= 360.0 / 65535.0
    sat /= 65535.0
    brightness /= 65535.0
    return (hue, sat, brightness, kelvin)


def hsbk_machine(hsbk: Union[Tuple, List]) -> Tuple:
    """Make hsbk machine readable"""
    if not isinstance(hsbk, (tuple, list)):
        raise ValueError("hsbk must be a len 4 tuple/list")

    if not len(hsbk) == 4:
        raise ValueError("hsbk must have exactly 4 items.")

    hue, sat, brightness, kelvin = hsbk
    hue = int(hue * 65535 / 360.0) % 65535
    sat = int(sat * 65535)
    brightness = int(brightness * 65535)
    kelvin = int(kelvin)
    return (hue, sat, brightness, kelvin)


def is_str_ipaddr(ipaddr: str) -> bool:
    if re.match(r"(\d+)\.(\d+)\.(\d+)\.(\d+)", ipaddr) is None:
        return False

    try:
        ip_nums = map(int, ipaddr.split("."))
        nums_valid = [0 <= n <= 255 for n in ip_nums]
    except ValueError:
        return False

    return all(nums_valid)


def is_str_mac(mac: str) -> bool:
    if re.match(r"(\S\S):" * 5 + r"(\S\S)", mac) is None:
        return False

    try:
        mac_nums = [int("0x" + ch, 16) for ch in mac.split(":")]
        nums_valid = [0 <= n <= 255 for n in mac_nums]
    except ValueError:
        return False

    return all(nums_valid)


def mac_int_to_str(mac_int: int) -> str:
    mac_size = 6  # number of bytes in mac address
    mac_hex = struct.pack("Q", mac_int)[:mac_size].hex()
    return ":".join([mac_hex[2 * i : 2 * i + 2] for i in range(mac_size)])  # noqa


def mac_str_to_int(mac_str: str) -> int:
    # Swap endianness, then convert to an integer
    hex_str = "0x" + "".join(reversed(mac_str.split(":")))
    return int(hex_str, 16)


def mac_str_to_int_list(mac_str: str) -> List[int]:
    mac_int = mac_str_to_int(mac_str)
    int_list: List[int] = []
    for _ in range(8):
        int_list.append(mac_int % (1 << 8))
        mac_int = mac_int >> 8
    return int_list


def rgba2hsbk(rgba_tuple: (tuple, list), kelvin: (int, float)):
    """
    Convert RGBA to HSBK.

    Assume max(rgba) == 1

    kelvin mainly sets white balance for photography.
    """
    if not isinstance(rgba_tuple, (tuple, list)):
        raise ValueError("rgba_tuple must be a len 4 tuple/list")

    if not len(rgba_tuple) == 4:
        raise ValueError("rgba_tuple must have exactly 4 items.")

    red, green, blue, alpha = rgba_tuple
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
    brightness = max_col

    return (hue, sat, brightness, kelvin)
