#!/usr/bin/env python3

from matplotlib import colors

from lifxdev.colors import color
from lifxdev.devices import light
from lifxdev.messages import tile_messages
from lifxdev.messages import packet

TILE_WIDTH = 8


class LifxTile(light.LifxLight):
    """Tile device control"""

    def __init__(self, *args, length: int | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._num_tiles: int | None = length

    def get_chain(self) -> packet.LifxResponse:
        """Get information about the current tile chain"""
        response = self.send_recv(tile_messages.GetDeviceChain(), res_required=True)
        assert response is not None
        response = response.pop()
        self._num_tiles = response.payload["total_count"]
        return response

    def get_num_tiles(self) -> int:
        """Get the number of tiles that can be controlled"""
        if self._num_tiles:
            return self._num_tiles
        else:
            return self.get_chain().payload["total_count"]

    def get_tile_colors(self, tile_index: int, *, length: int = 1) -> list[list[color.Hsbk]]:
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
        assert responses is not None
        matrix_list: list[list[color.Hsbk]] = []
        for state in responses:
            matrix_list.append([color.Hsbk.from_packet(hsbk) for hsbk in state.payload["colors"]])
        return matrix_list

    def set_colormap(
        self,
        cmap: str | colors.Colormap,
        *,
        duration: float = 0.0,
        kelvin: int = color.KELVIN,
        division: int = 2,
        ack_required: bool = False,
    ) -> packet.LifxResponse | None:
        """Set the tile chain to a matplotlib colormap.

        Args:
            cmap_name: (str) Name or object of a matplotlib colormap.
            duration: (float) The time in seconds to make the color transition.
            kelvin: Color temperature of white colors in the colormap.
            division: How much to subdivide the tiles (must be in [1, 2, 4]).
            ack_required: (bool) True gets an acknowledgement from the device.
        """
        if division not in [1, 2, 4]:
            raise ValueError("Cannot evenly subdivide tiles.")
        num_tiles = self.get_num_tiles()
        sq_width = TILE_WIDTH // division
        sq_per_tile = division**2
        colormap = color.get_colormap(cmap, num_tiles * sq_per_tile, kelvin, randomize=True)

        # This is hard to not be some gnarly for loop
        response: packet.LifxResponse | None = None
        for ii in range(num_tiles):
            colors_per_tile = [
                color.Hsbk(hue=0, saturation=0, brightness=0, kelvin=0)
            ] * TILE_WIDTH**2
            for jj in range(sq_per_tile):
                col = jj % division
                row = jj // division
                for kk in range(sq_width**2):
                    sq_col = kk % sq_width
                    sq_row = kk // sq_width
                    tile_idx = sq_col + col * sq_width + TILE_WIDTH * (sq_row + row * sq_width)
                    color_idx = ii * sq_per_tile + row * division + col
                    colors_per_tile[tile_idx] = colormap[color_idx]

            response = self.set_tile_colors(
                ii,
                colors_per_tile,
                duration=duration,
                ack_required=ack_required,
            )
        return response

    def set_tile_colors(
        self,
        tile_index: int,
        tile_colors: list[color.Hsbk],
        *,
        duration: float = 0.0,
        length: int = 1,
        ack_required: bool = False,
    ) -> packet.LifxResponse | None:
        """Set the tile colors

        Args:
            tile_index: (int) The tile index in the chain to query.
            tile_colors: List of colors to set the tile(s) to.
            duration: (float) The time in seconds to make the color transition.
            length: (int) The number of tiles to query.
            ack_required: (bool) True gets an acknowledgement from the device.
        """
        set_request = tile_messages.SetTileState64(width=TILE_WIDTH)
        set_request["tile_index"] = tile_index
        set_request["length"] = length
        set_request["duration"] = int(duration * 1000)
        set_request["colors"] = [
            hsbk_tuple.max_brightness(self.max_brightness).to_packet()
            for hsbk_tuple in map(color.Hsbk.from_tuple, tile_colors)
        ]
        return self.send_msg(set_request, ack_required=ack_required)
