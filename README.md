# lifxdev
LIFX device control over LAN

### NOTE
This is a personal project that I update infrequently. Things might not be
fully documented and this might be subject to breakage.

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

## Usage

The heart of `lifxdev` is the telnet interface used to manage scripts and
change lights/strips. The script `run-lifx-server.py` initializes the telnet
server that users can access to control processes and lights. After logging
into the server via telnet, the `help` command will list the shell commands.

Accessing the server via telnet:

```
telnet IP_OF_SERVER 16384
```

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
scripts controlling the same devices don't clash. If a script is a Python
script, then the same Python executable used to run the LIFX server is used to
run the script. If the script isn't a Python script, then it's run as is.
