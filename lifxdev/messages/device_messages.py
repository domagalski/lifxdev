#!/usr/bin/env pythom3

"""Device messages


"""

from lifxdev.messages import packet


@packet.set_message_type(2)
class GetService(packet.LifxMessage):
    pass
