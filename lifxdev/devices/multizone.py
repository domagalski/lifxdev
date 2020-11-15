#!/usr/bin/env python3

from typing import List, Optional, Union

from matplotlib import colors

from lifxdev.colors import color
from lifxdev.devices import light
from lifxdev.messages import multizone_messages
from lifxdev.messages import packet


class LifxMultiZone(light.LifxLight):
    """MultiZone device (beam, strip) control"""

    _num_zones: Optional[int] = None

    def get_multizone(self) -> List[color.Hsbk]:
        """Get a list the colors on the MultiZone.

        Returns:
            List of human-readable HSBK tuples representing the device.
        """
        response = self.send_recv(multizone_messages.GetExtendedColorZones(), res_required=True)
        payload = response[0].payload
        self._num_zones = payload["count"]
        multizone_colors = payload["colors"][: self._num_zones]
        return [color.Hsbk.from_packet(cc) for cc in multizone_colors]

    def get_num_zones(self) -> int:
        """Get the number of zones that can be controlled"""
        if self._num_zones:
            return self._num_zones
        else:
            return len(self.get_multizone())

    def set_colormap(
        self,
        cmap: Union[str, colors.Colormap],
        *,
        duration: float = 0.0,
        kelvin: int = color.KELVIN,
        ack_required: bool = False,
    ) -> Optional[packet.LifxResponse]:
        """Set the zone to a matplotlib colormap.

        Args:
            cmap_name: (str) Name or object of a matplotlib colormap.
            duration: (float) The time in seconds to make the color transition.
            kelvin: Color temperature of white colors in the colormap.
            ack_required: (bool) True gets an acknowledgement from the device.
        """
        num_zones = self.get_num_zones()
        colormap = color.get_colormap(cmap, num_zones, kelvin)
        return self.set_multizone(colormap, duration=duration, ack_required=ack_required)

    def set_multizone(
        self,
        multizone_colors: List[color.Hsbk],
        *,
        duration: float = 0.0,
        index: int = 0,
        ack_required: bool = False,
    ) -> Optional[packet.LifxResponse]:
        """Set the MultiZone colors.

        Args:
            multizone_colors: (list) A list of human-readable HSBK tuples to set.
            duration: (float) The time in seconds to make the color transition.
            index: (int) MultiZone starting position of the first element of colors.
            ack_required: (bool) True gets an acknowledgement from the device.
        """
        set_colors = multizone_messages.SetExtendedColorZones()
        set_colors["apply"] = multizone_messages.ApplicationRequest.APPLY
        set_colors["duration"] = int(duration * 1000)
        set_colors["index"] = index
        set_colors["colors_count"] = len(multizone_colors)
        for ii, hsbk in enumerate(multizone_colors):
            set_colors.set_value(
                "colors",
                color.Hsbk.from_tuple(hsbk).max_brightness(self.max_brightness).to_packet(),
                index + ii,
            )
        return self.send_msg(set_colors, ack_required=ack_required)
