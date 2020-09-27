#!/usr/bin/env python3

from typing import List, Optional

from lifxdev.devices import light
from lifxdev.messages import multizone_messages
from lifxdev.messages import packet


class LifxMultiZone(light.LifxLight):
    """MultiZone device (beam, strip) control"""

    def get_multizone(self) -> List[light.Hsbk]:
        """Get a list the colors on the MultiZone.

        Returns:
            List of human-readable HSBK tuples representing the device.
        """
        response = self.send_recv(multizone_messages.GetExtendedColorZones(), res_required=True)
        payload = response[0].payload
        count = payload["count"]
        colors = payload["colors"][:count]
        return [light.Hsbk.from_packet(cc) for cc in colors]

    def set_multizone(
        self,
        colors: List[light.Hsbk],
        duration_s: float,
        *,
        index: int = 0,
        ack_required=True,
    ) -> Optional[packet.LifxResponse]:
        """Set the MultiZone colors.

        Args:
            colors: (list) A list of human-readable HSBK tuples to set.
            duration_s: (float) The time in seconds to make the color transition.
            index: (int) MultiZone starting position of the first element of colors.
            ack_required: (bool) True gets an acknowledgement from the device.
        """
        set_colors = multizone_messages.SetExtendedColorZones()
        set_colors["apply"] = multizone_messages.ApplicationRequest.APPLY
        set_colors["duration"] = int(duration_s * 1e3)
        set_colors["index"] = index
        set_colors["colors_count"] = len(colors)
        for ii, color in enumerate(colors):
            set_colors.set_value("colors", color.to_packet(), index + ii)
        response = self.send_recv(set_colors, ack_required=ack_required)
        if response:
            return response[0]
