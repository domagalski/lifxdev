#!/usr/bin/env python3

from typing import List, Optional, Union

from matplotlib import colors

from lifxdev.colors import color
from lifxdev.devices import light
from lifxdev.messages import tile_messages
from lifxdev.messages import packet

TILE_WIDTH = 8


class LifxTile(light.LifxLight):
    """Tile device control"""

    _num_tiles: Optional[int] = None

    def get_chain(self) -> packet.LifxResponse:
        """Get information about the current tile chain"""
        response = self.send_recv(tile_messages.GetDeviceChain(), res_required=True).pop()
        self._num_tiles = response.payload["total_count"]
        return response

    def get_num_tiles(self) -> int:
        """Get the number of tiles that can be controlled"""
        if self._num_tiles:
            return self._num_tiles
        else:
            return self.get_chain().payload["total_count"]

    def get_tile_colors(self, tile_index: int, *, length: int = 1) -> List[List[color.Hsbk]]:
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
        matrix_list: List[List[color.Hsbk]] = []
        for state in responses:
            matrix_list.append([color.Hsbk.from_packet(hsbk) for hsbk in state.payload["colors"]])
        return matrix_list

    def set_colormap(
        self,
        cmap: Union[str, colors.Colormap],
        duration_s: float,
        *,
        kelvin: int = color.KELVIN,
        division: int = 2,
        ack_required: bool = True,
    ) -> Optional[packet.LifxResponse]:
        """Set the tile chain to a matplotlib colormap.

        Args:
            cmap_name: (str) Name or object of a matplotlib colormap.
            duration_s: (float) The time in seconds to make the color transition.
            kelvin: Color temperature of white colors in the colormap.
            division: How much to subdivide the tiles (must be in [1, 2, 4]).
            ack_required: (bool) True gets an acknowledgement from the device.
        """
        if division not in [1, 2, 4]:
            raise ValueError("Cannot evenly subdivide tiles.")
        num_tiles = self.get_num_tiles()
        sq_width = TILE_WIDTH // division
        sq_per_tile = division ** 2
        colormap = color.get_colormap(cmap, num_tiles * sq_per_tile, kelvin, randomize=True)

        # This is hard to not be some gnarly for loop
        response: Optional[packet.LifxResponse] = None
        for ii in range(num_tiles):
            colors_per_tile = [None] * TILE_WIDTH ** 2
            for jj in range(sq_per_tile):
                col = jj % division
                row = jj // division
                for kk in range(sq_width ** 2):
                    sq_col = kk % sq_width
                    sq_row = kk // sq_width
                    tile_idx = sq_col + col * sq_width + TILE_WIDTH * (sq_row + row * sq_width)
                    color_idx = ii * sq_per_tile + row * division + col
                    colors_per_tile[tile_idx] = colormap[color_idx]

            response = self.set_tile_colors(
                ii,
                colors_per_tile,
                duration_s,
                ack_required=ack_required,
            )
        return response

    def set_tile_colors(
        self,
        tile_index: int,
        tile_colors: List[color.Hsbk],
        duration_s: float,
        *,
        length: int = 1,
        ack_required: bool = True,
    ) -> Optional[packet.LifxResponse]:
        """Set the tile colors

        Args:
            tile_index: (int) The tile index in the chain to query.
            tile_colors: List of colors to set the tile(s) to.
            duration_s: (float) The time in seconds to make the color transition.
            length: (int) The number of tiles to query.
            ack_required: (bool) True gets an acknowledgement from the device.
        """
        set_request = tile_messages.SetTileState64(width=TILE_WIDTH)
        set_request["tile_index"] = tile_index
        set_request["length"] = length
        set_request["duration"] = int(duration_s * 1000)
        set_request["colors"] = [color.Hsbk.from_tuple(hsbk).to_packet() for hsbk in tile_colors]
        return self.send_msg(set_request, ack_required=ack_required)
