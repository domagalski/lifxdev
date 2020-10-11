# lifxdev
LIFX device control over LAN

## Installation

Dependencies can be installed from the requirements file:

```
pip install -r requirements.txt
```

Once dependencies are installed, `lifxdev` can be installed normally:

```
sudo python setup.py install
```

`lifxdev` has been tested on Linux in Ubuntu 20.04 and on the Raspberry Pi.

## Security

LIFX lights can be controlled by anyone on name same WiFi network as you. So
can the ZMQ server scripts in this repository. Please determine your WiFi
network configurations accordingly.

## Usage

Please see the configuration session, as it is required for running the scripts
from the scripts directory.

The heart of `lifxdev` is the ZMQ interface used to manage scripts and
change lights/strips. The script `lifx-server` initializes the ZMQ server that
users can access to control processes and lights. The client command
`lifx-client help` displays all available commands.

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
  type: bulb
  mac: <mac_addr>
  ip: <ip_addr>

example-group:
  type: group
  devices:
    device-name-a:
      type: multizone
      mac: <mac_addr>
      ip: <ip_addr>
    device-name-b:
      type: bulb
      mac: <mac_addr>
      ip: <ip_addr>
    subgroup-name:
      type: group
      devices: ...
```

Items in the config can be either devices or groups, indicated by the `type`
field, which is required for every device or group in the configuration. The
value for `type` can be either `light`, `infrared`, `multizone`, or `tile`.
Each device also requires that its MAC and IP are provided.

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
