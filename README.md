# lifxdev
LIFX device control over LAN

### NOTE
This is a personal project that I update infrequently. Things might not be
fully documented or stable.

## Installation

Dependencies can be installed from the requirements file:

```
pip install -r requirements.txt
```

Once dependencies are intalled, `lifxdev` can be installed normally:

```
sudo python setup.py install
```

`lifxdev` has been tested on Linux in Ubuntu 18.04 and on the Raspberry Pi.

## Security

LIFX lights can be controlled by anyone on name same WiFi network as you. So
can the telnet server scripts in this repository. Please determine your WiFi
network configurations accordingly.

## Usage

Please see the configuration session, as it is required for running the scripts
from the scripts directory.

The heart of `lifxdev` is the telnet interface used to manage scripts and
change lights/strips. The script `run-lifx-server.py` initializes the telnet
server that users can access to control processes and lights. After logging
into the server via telnet, the `help` command will list the shell commands.

Accessing the server via telnet:

```
telnet IP_OF_SERVER 16384
```

The script `dhcp-trigger-lifx.py` works with `dnsmasq` to act as a trigger for
when certain devices with known MAC addresses connect to your WiFi network. I
use [Pi-Hole](https://pi-hole.net/) as my provider of `dnsmasq` for running
`dhcp-trigger-lifx.py`. See the `~/.lifx/monitor_mac.yaml` subsection of the
configuration for instructions on how to set this up and use it.

## Configuration

`lifxdev` is based on configuration files. They live in the `~/.lifx`
directory. These configuration files are pretty much necessary for `lifxdev` to
work, so let's discuss them here.

### ~/.lifx/device_config.yaml

The `device_config.yaml` file is a registry of LIFX devices and device groups.
It's recommended to use DHCP reservations with your router to ensure the IP
address of each LIFX device never changes. Here's an example
`device_config.yaml` file:

```
example-device:
  type: bulb
  mac: <mac_addr>
  ip: <ip_addr>

example-group:
  type: group
  devices:
    - device-name-a:
        type: multizone
        mac: <mac_addr>
        ip: <ip_addr>
    - device-name-b:
        type: bulb
        mac: <mac_addr>
        ip: <ip_addr>
    - subgroup-name:
        type: group
        devices: ...
```

Items in the config can be either devices or groups, indicated by the `type`
field, which is required for every device or group in the configuration. The
value for `type` can be either `bulb`, `multizone`, or `tile`. Each device also
requires that its MAC and IP are provided.

Groups require the `type: group` field and the `devices` field that's a list of
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
lists any devices in `device_config.yaml` that the script contains so that two
scripts controlling the same devices don't clash. The `immortal` field, which
is optional, determines whether `killall` commands can kill the process. If a
script is a Python script, then the same Python executable used to run the LIFX
server is used to run the script. If the script isn't a Python script, then
it's run as is.

### ~/.lifx/monitor_mac.yaml

Hi Twitter! This might not be stable enough for production usage, but here it
is for those interested.

The `monitor_mac.yaml` file is used to configure the `dhcp-trigger-lifx.py`
script. See the next section on how to use Pi-Hole/dnsmasq with this script.
Here's an example of the `monitor_mac.yaml` file with the default values for
each field:

```
port: 16385
enabled: true
lifx_addr: 127.0.0.1
lifx_port: 16384
grace_minutes: 0
lease_file: /etc/pihole/dhcp.leases

lifx_commands:
  alarm: start alarm
  home: start home

mac_addrs:
  - <mac_addr_1>
  - <mac_addr_2>

alarm:
  - <mac_addr_3>
  - <mac_addr_4>
```

* The `port` tells which which TCP port for the trigger to listen on. This must
be different than the `lifx_port` field, which tells which port the LIFX telnet
server listens on.
* The `enabled` field tells whether or not to activate any commands when a
known MAC address connects.
* The `lifx_addr` and `lifx_port` fields tell the IP address and TCP port of
the LIFX telnet server.
* The `grace_minutes` is experimental and shouldn't be modified.
* The `lease_file` script determines where the dhcp leases are. The default is
for the [Pi-Hole](https://pi-hole.net/) software.
* The `lifx_commands` field determines which LIFX server functions are run for
various scenarios. The default is to start a process named `alarm` defined in
the `processes.yaml` file for when MAC addresses from the `alarm` list connect
to your WiFi and the `home` process when any MAC in `mac_addrs` connects.
* The `mac_addrs` field is a list of MAC addresses that you want to trigger a
the `home` command. An example of an address for this would be a personal cell
phone.
* The `alarm` field is a list of MAC addresses that trigger the `alarm`
command. I have the MAC address of the person from the bad hookup that inspired
this functionality in my `alarm` list.

#### Configuring the DHCP script trigger

The `dhcp-trigger-lifx.py` script needs TCP packets of the following format
sent to it:

```
<state> <mac_addr> <ip_addr>
```

This can be done automatically with PiHole or dnsmasq via the dhcp-scripts
option. The file `dhcp-trigger/99-dhcp-script.conf` in this repo needs to be
put in the `/etc/dnsmasq.d/` directory (restart PiHole after doing this). The
script `dhcp-trigger/dhcp-lifx.sh` script needs to be put in `/usr/local/bin`
on whatever machine you want to use to run the trigger. The IP and port in the
telnet command on that script should be edited to the IP address and port to
where `dhcp-trigger-lifx.py` is running and listening on.
