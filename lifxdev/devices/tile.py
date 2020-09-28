#!/usr/bin/env python3

from typing import List, Optional

from lifxdev.devices import light
from lifxdev.messages import tile_messages
from lifxdev.messages import packet

TILE_WIDTH = 8


class LifxTile(light.LifxLight):
    """Tile device control"""

    def get_chain(self) -> packet.LifxResponse:
        """Get information about the current tile chain"""
        response = self.send_recv(tile_messages.GetDeviceChain(), res_required=True)
        return response[0]

    def get_tile_colors(self, tile_index: int, *, length: int = 1) -> List[List[light.Hsbk]]:
        """Get the color state for individual tiles.

        Args:
            tile_index: (int) The tile index in the chain to query.
            length: (int) The number of tiles to query.

        Returns:
            List of tile states.
        """
        get_request = tile_messages.GetTileState64(width=TILE_WIDTH)
        get_request["tile_index"] = tile_index
        get_request["length"] = length
        responses = self.send_recv(get_request, res_required=True, retry_recv=length > 1)
        matrix_list: List[List[light.Hsbk]] = []
        for state in responses:
            matrix_list.append([light.Hsbk.from_packet(hsbk) for hsbk in state.payload["colors"]])
        return matrix_list

    def set_tile_colors(
        self,
        tile_index: int,
        colors: List[light.Hsbk],
        duration_s: float,
        *,
        length: int = 1,
        ack_required: bool = True,
    ) -> Optional[packet.LifxResponse]:
        """Set the tile colors

        Args:
            tile_index: (int) The tile index in the chain to query.
            colors: List of colors to set the tile(s) to.
            duration_s: (float) The time in seconds to make the color transition.
            length: (int) The number of tiles to query.
            ack_required: (bool) True gets an acknowledgement from the device.
        """
        set_request = tile_messages.SetTileState64(width=TILE_WIDTH)
        set_request["tile_index"] = tile_index
        set_request["length"] = length
        set_request["duration"] = int(duration_s * 1000)
        set_request["colors"] = [hsbk.to_packet() for hsbk in colors]
        return self.send_msg(set_request, ack_required=ack_required)
