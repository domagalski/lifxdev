#!/usr/bin/env python3

from typing import Optional

from lifxdev.colors import color
from lifxdev.devices import device
from lifxdev.messages import light_messages
from lifxdev.messages import packet


class LifxLight(device.LifxDevice):
    """Light control"""

    def get_color(self) -> color.Hsbk:
        """Get the color of the device

        Returns:
            The human-readable HSBK of the light.
        """
        response = self.send_recv(light_messages.Get(), res_required=True)
        return color.Hsbk.from_packet(response.pop().payload["color"])

    def get_power(self) -> bool:
        """Get the power state of the light.

        Returns:
            True if the light is powered on. False if off.
        """
        response = self.send_recv(light_messages.GetPower(), res_required=True)
        return response.pop().payload["level"]

    def set_color(
        self,
        hsbk: color.Hsbk,
        duration_s: float,
        *,
        ack_required: bool = True,
    ) -> Optional[packet.LifxResponse]:
        """Set the color of the light.

        Args:
            hsbk: (color.Hsbk) Human-readable HSBK tuple.
            duration_s: (float) The time in seconds to make the color transition.
            ack_required: (bool) True gets an acknowledgement from the light.

        Returns:
            If ack_required, then get a color tuple as a response, else None.
        """
        hsbk = color.Hsbk.from_tuple(hsbk)
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
        ir_state = response.pop().payload
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
