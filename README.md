# lifxdev
LIFX device control over LAN

## Installation

Dependencies can be installed from the requirements file:

```
# Requirements for the core library.
pip install -r requirements.txt

# Requirements for the testing/development.
pip install -r requirements-dev.txt
```

Once dependencies are installed, `lifxdev` can be installed normally:

```
sudo python setup.py install
```

`lifxdev` has been tested on Linux in Ubuntu 20.04 and on the Raspberry Pi.

## Security

LIFX lights can be controlled by anyone on name same WiFi network as you. So
can the TCP server scripts in this repository. Please determine your WiFi
network configurations accordingly.

## Usage

`lifxdev` can either be used as the server/client commands or via a Python
module to control individual devices in scripts.

The `lifx-dhcp-trigger.py` script is an example script built using the
`lifxdev` API to control lights in response to DHCP connections reported by
`dnsmasq`. See the DHCP trigger subsection in the configuration section for
instructions on using it.

### LIFX server usage

To start the server, run `lifx-server`.

Please see the configuration section for setting up the configuration files
needed to use the server. The client command `lifx-client help` displays all
available commands when the server is running. It is assumed that `lifx-server`
is running in the following examples.

#### Setting the color of all devices in a group

The server device config must have a group called "living-room" for this.

```
lifx-client --ip $SERVER_IP color living-room 0 1 1 5500
```

#### Starting/stopping a process

The server process config must have a process called "light-shuffle" for this.

```
# Start the process
lifx-client --ip $SERVER_IP start light-shuffle

# Verify that light-shuffle is a running process
lifx-client --ip $SERVER_IP list

# Check if any running processes have errors
lifx-client --ip $SERVER_IP check

# Start the process
lifx-client --ip $SERVER_IP stop light-shuffle
```

Once a process is started, `start` cannot be called twice without error. If a
process needs to be restarted, the `restart` command stops it before restarting
it.

### Usage as a Python module

`lifxdev` is a series of Python modules. Module overview:

- `lifxdev.colors`: Module for color operations used by devices.
- `lifxdev.devices`: The main module for controlling LIFX devices. This is
probably the most useful module. Lights, IR, MultiZone (beam/strip), and Tiles
can be controlled via `lifxdev.devices`.
- `lifxdev.messages`: LIFX control message generation.
- `lifxdev.server`: LIFX server implementation.

#### Controlling a bulb

```python

from lifxdev.devices import light

bulb = light.LifxLight(device_ip, label="Lamp")
bulb.set_power(True, duration_s=0)
# Colors are (hue, saturation, brighness, kelvin)
bulb.set_color((0, 1, 1, 5500), duration_s=0)
```

#### Controlling a light strip

```python

from lifxdev.devices import multizone

strip = multizone.LifxMultiZone(device_ip, label="Light Strip")
strip.set_power(True, duration_s=0)
strip.set_color((0, 1, 1, 5500), duration_s=0)
# color_list is a list of HSBK tuples
strip.set_multizone(color_list, duration_s=0)
# Any matplotlib colormap can be used.
strip.set_colormap("cool", duration_s=0)
```

#### Getting devices via the DeviceManager

The device manager is useful when controlling devices with known IP addresses,
such as one's personal LIFX devices, as their configuration is unlikely to
change.

```python

from lifxdev.devices import device_manager

dm = device_manager.DeviceManager()
bulb = dm.get_device(bulb_name)
strip = dm.get_device(strip_name)
tile = dm.get_device(tile_name)
```

#### Talking to a LIFX server

Talking to a LIFX server from within a Python script is relatively
straightforward and is useful for automating pre-configured processes.

```python

from lifxdev.server import client

lifx = client.LifxClient(server_ip)
# This either prints the response message or raises the server error.
print(lifx("start light-shuffle"))
```

## Configuration

`lifxdev` is based on configuration files. They live in the `~/.lifx`
directory. These configuration files are pretty much necessary for `lifxdev` to
work, so let's discuss them here.

### ~/.lifx/devices.yaml

The `devices.yaml` file is a registry of LIFX devices and device groups.
It's recommended to use DHCP reservations with your router to ensure the IP
address of each LIFX device never changes. Here's an example `devices.yaml`
file:

```
example-device:
  type: light
  ip: <ip_addr>

example-group:
  type: group
  devices:
    device-name-a:
      type: multizone
      ip: <ip_addr>
    device-name-b:
      type: light
      ip: <ip_addr>
    subgroup-name:
      type: group
      devices: ...
```

Items in the config can be either devices or groups, indicated by the `type`
field, which is required for every device or group in the configuration. The
value for `type` can be either `light`, `infrared`, `multizone`, or `tile`.
Each device also requires that its IP address is provided.

Groups require the `type: group` field and the `devices` field that's a dict of
devices or sub-groups. There's no maximum recursion depth for groups, so a
config can have arbitrary amounts of subgroups. There's also no requirement
that devices belong to any groups.

### ~/.lifx/processes.yaml

Here's the overall structure of the `processes.yaml` file:

```
PROC_DIR: directory/where/your/scripts/live

example-script:
  filename: script_name.py
  ongoing: true/false
  immortal: true/false
  devices:
    - device-a
    - device-b
```

The field `PROC_DIR` is required, as it tells where processes live.

Processes are started in the telnet shell with the command
`start example-script`. Each script in `processes.yaml` required the
`filename` field. The `ongoing` field determines whether the script exits
immediately after running it and configuring lights or if the script continues
running indefinitely. It is optional. The `devices` field, also optional,
lists any devices in `devices.yaml` that the script contains so that two
scripts controlling the same devices don't clash. The `immortal` field, which
is optional, determines whether `killall` commands can kill the process. If a
script is a Python script, then the same Python executable used to run the LIFX
server is used to run the script. If the script isn't a Python script, then
it's run as is.

### ~/.lifx/dhcp-trigger.yaml

This is completely optional and only required when using the script
`lifx-dhcp-trigger.py` in `dhcp-trigger`. The DHCP trigger script is not a part
of the `lifxdev` API, but is built on top of it.

The DHCP trigger script can be run as such:
```
cd dhcp-trigger
python3 lifx-dhcp-trigger.py
```

This listens on a TCP port (default 16385) for messages with the format:
```
state mac_address ip_address
```

If the mac address is in the config, then a LIFX server command will be ran
based on the configuration for it. Typically, I use the
[Pi-Hole](https://pi-hole.net/) software as a `dnsmasq` server to generate
these messages. To do this, the file `99-dhcp-script.conf` in `dhcp-trigger`
must be placed in `/etc/dnsmasq.d` to configure the script used
to process DHCP connections. The script `dhcp-lifx.sh` in `dhcp-trigger` must
be placed wherever it is referenced by `99-dhcp-script.conf`. Those two files
should probably be edited for one's unique setup.

#### DHCP Trigger configuration

The file `~/.lifx/dhcp-trigger.yaml` must be configured as follows:
```
<cmd_label>:
  command: <lifx_server_command>
  macs:
    - <mac_addr_1>
    - <mac_addr_2>
    - ...
```

The `cmd_label` is any label to denote the name of a list of MAC addresses and
the LIFX server command to run when one of those MAC addresses is detected. As
such, multiple command labels can be listed in a configuration file. The only
real requirement is that there is a `command` field nested under each label
containing a single LIFX server command.
