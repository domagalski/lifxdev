#!/usr/bin/env python3

import os
import time
import socket
import threading as th
import subprocess as spr
from threading import Thread

import yaml

from lifxdev.logs import get_logger

DEFAULT_LEASE_FILE = "/etc/pihole/dhcp.leases"
DEFAULT_GRACE_MINUTES = 0
DEFAULT_LIFX_ADDR = "127.0.0.1"
DEFAULT_LIFX_PORT = 16384
DEFAULT_PORT = 16385


class IPMonitor(object):
    def __init__(self, monitor_filename):
        """
        Initialize a monitor with a whitelist.
        """
        self.logger = get_logger()
        self.monitor_filename = monitor_filename
        try:
            with open(self.monitor_filename) as f:
                config = yaml.safe_load(f)
        except Exception:
            self.logger.warning("Cannont load config file: {}".format(self.monitor_filename))
            config = {}

        self.init_mac_dict()

        # Get configuration options
        self.lease_file = config.get("lease_file", DEFAULT_LEASE_FILE)
        self.grace_minutes = config.get("grace_minutes", DEFAULT_GRACE_MINUTES)
        self.lifx_addr = config.get("lifx_addr", DEFAULT_LIFX_ADDR)
        self.lifx_port = config.get("lifx_port", DEFAULT_LIFX_PORT)
        self.port = config.get("port", DEFAULT_PORT)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("", self.port))
        self.sock.listen(5)

        lifx_commands = config.get("lifx_commands", {})
        self.lifx_commands = {
            "home": lifx_commands.get("home", "start home"),
            "alarm": lifx_commands.get("home", "start alarm"),
        }

    def check_state(self, coming_online):
        """
        Check the state and perform an action based on whether devices
        are coming online or going offline.
        """

        def _online(m):
            return self.mac_addrs[m]["last_connect"] > self.mac_addrs[m]["last_disconnect"]

        with open(self.monitor_filename) as f:
            config = yaml.safe_load(f)

        if not config.get("enabled", False):
            return

        dev_online = [_online(mac) for mac in self.mac_addrs]

        # if one device is online, then trigger is eligable
        grace_time = self.grace_minutes * 60
        if sum(dev_online) == 0:
            conn = [self.mac_addrs[m]["last_connect"] for m in self.mac_addrs]

            # only start if last connect time is longer than five minutes
            if time.time() - max(conn) > grace_time:
                self.send_cmd("off")

        elif sum(dev_online) == 1 and coming_online:
            disconn = [self.mac_addrs[m]["last_disconnect"] for m in self.mac_addrs]

            # only start if last disconnect time is longer than five minutes
            if time.time() - max(disconn) > grace_time:
                self.send_cmd(self.lifx_commands["home"])

    def get_ip(self, mac):
        return self.mac_addrs[mac]["ip"]

    def init_mac_dict(self):
        """
        Initialize a dictionary of the mac addresses to be monitored.
        """
        with open(self.monitor_filename) as f:
            config = yaml.safe_load(f)

        init_dict = {"ip": None, "last_connect": 0, "last_disconnect": 0}
        # 'thread': None}
        self.mac_addrs = {mac.lower(): init_dict.copy() for mac in config.get("mac_addrs", [])}
        self.alarm_addr = {mac.lower(): init_dict.copy() for mac in config.get("alarm", [])}

    def is_reachable(self, ip_addr):
        """
        ping an address and return true if reachable
        """
        ping_cmd = ["ping", "-c", "1", "-w", "1", ip_addr]
        proc = spr.call(ping_cmd, stdout=spr.DEVNULL, stderr=spr.DEVNULL)
        return not proc

    def monitor_mac(self, mac, initial_state):
        """
        Monitor a mac address for changes in whether or not it's reachable
        """
        ip_addr = self.get_ip(mac)
        current_state = self.is_reachable(ip_addr)

        # rising edge
        if current_state and not initial_state:
            self.logger.info("Device {} with IP {} online.".format(mac, self.get_ip(mac)))
            self.mac_addrs[mac]["last_connect"] = time.time()
            self.check_state(True)

        # falling edge
        if not current_state and initial_state:
            self.logger.info("Device {} with IP {} offline.".format(mac, self.get_ip(mac)))
            self.mac_addrs[mac]["last_disconnect"] = time.time()
            self.check_state(False)

    def startup(self):
        """
        Examine why I decided to write this function...
        """
        if not os.path.exists(self.lease_file):
            return

        with open(self.lease_file) as f:
            lease_lines = f.readlines()

        for line in lease_lines:
            lease = line.split()
            mac = lease[1]
            ipaddr = lease[2]

            if mac in self.mac_addrs:
                self.logger.info(mac)
                self.mac_addrs[mac]["ip"] = ipaddr
                is_online = self.is_reachable(ipaddr)
                if is_online:
                    self.mac_addrs[mac]["last_connect"] = time.time()
                    self.logger.info("Device {} with IP {} online.".format(mac, self.get_ip(mac)))

                self.mac_addrs[mac]["thread"] = th.Thread(target=self.monitor_mac, args=(mac, is_online))
                self.mac_addrs[mac]["thread"].daemon = True
                self.mac_addrs[mac]["thread"].start()

    def send_cmd(self, cmd):
        """
        Quickly send a lifx command to a socket
        """
        try:
            self.logger.info("Sending LIFX command: '{}'".format(cmd))
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.lifx_addr, self.lifx_port))
            s.recv(4096)
            s.send(str.encode(cmd))
            s.recv(4096)
            s.close()
        except ConnectionRefusedError:
            self.logger.error(
                "Cannot send command '{}' to LIFX endpoint: {}:{}".format(cmd, self.lifx_addr, self.lifx_port)
            )

    def update(self):
        """
        Wait for devices to connect, then check their monitoring threads
        """
        # Get information from dhcp-script
        conn, addr = self.sock.accept()
        ip_info = bytes.decode(conn.recv(1024)).rstrip("\n").rstrip("\r")
        conn.close()

        ip_info_split = ip_info.split()
        if ip_info_split <= 3:
            return

        state, mac, ipaddr = ip_info_split[:3]
        mac = mac.lower()

        # NOTE: disconnect states must be sent from the phone via SSH over mobile data.
        if state not in ["add", "old", "disconnect"]:
            return

        updater_handler = Thread(target=self.updater_thread, args=(state, mac, ipaddr))
        updater_handler.daemon = True
        updater_handler.start()

    def updater_thread(self, state, mac, ipaddr):
        """
        TODO: write the docstring later lmao
        """
        ip_info = " ".join([state, mac, ipaddr])
        if mac in self.mac_addrs:
            self.logger.info(ip_info)

            # Wait until pingable to start monitoring
            while state in ["add", "old"] and not self.is_reachable(ipaddr):
                time.sleep(1)

            self.mac_addrs[mac]["ip"] = ipaddr
            self.monitor_mac(mac, state == "disconnect")

        if mac in self.alarm_addr:
            self.logger.info(ip_info)

            is_reachable = False
            for i in range(25):
                iter_start = time.time()
                if self.is_reachable(ipaddr):
                    is_reachable = True
                    break
                else:
                    time.sleep(max(0, 1 - (time.time() - iter_start)))

            if is_reachable:
                self.logger.info("Alarm activated: {}".format(mac))
                self.send_cmd(self.lifx_commands["alarm"])
            else:
                self.logger.info("cannot reach {} at {}.".format(mac, ipaddr))


if __name__ == "__main__":
    monitor = IPMonitor(os.path.join(os.environ["HOME"], ".lifx/monitor_mac.yaml"))
    # monitor.startup()
    while True:
        monitor.update()
