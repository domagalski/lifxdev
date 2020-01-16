#!/usr/bin/env python3

import os
import sys
import socket
import subprocess as spr
from threading import Thread

import yaml
import numpy as np
from matplotlib import cm
from numpy.random import random, shuffle

from lifxdev import DeviceManager, rgba2hsbk, get_logger, LIFXProcessConfigError

WHITE_KELVIN = 5000


class LIFXProcessServer(object):
    def __init__(self, avail_proc_yaml_file):
        self.logger = get_logger()
        self.avail_proc_yaml_file = avail_proc_yaml_file
        self.reload_conf(raise_err=True)

        # port to listen on
        self.port = 16384
        # Empty dictionary
        self.running_procs = {}

        # initialize the socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("", self.port))
        self.sock.listen(5)

        # prompt for the client
        self.prompt = b"LIFX> "

        self.device_manager = DeviceManager()
        self.device_manager.load_config(do_init_socket=True)

        # Color map names
        self.cmap_names = list(cm.cmap_d.keys())
        self.cmap_names += list(cm.cmaps_listed.keys())
        self.cmap_names = list(set(self.cmap_names))

    def check_running_procs(self, conn, send_reply=True):
        """
        Check running proccesses.
        """
        running_proc_names = list(self.running_procs.keys())

        check_str = ""
        for proc_name in running_proc_names:
            # check the return code of each process
            proc = self.running_procs[proc_name]["proc"]
            status_code = proc.poll()

            # None means the process is still running
            if status_code is None:
                continue

            # if the process has exited without error, quietly remove
            proc = self.running_procs.pop(proc_name)["proc"]
            if status_code:
                stdout, stderr = proc.communicate()
                if len(stdout):
                    stdout_str = bytes.decode(stdout)
                    check_str += f"{proc_name} stdout:\n{stdout_str}\n"
                if len(stderr):
                    stderr_str = bytes.decode(stderr)
                    check_str += f"{proc_name} stderr:\n{stderr_str}\n"

        if not len(check_str) and send_reply:
            check_str = "No processes with errors.\n"

        if len(check_str):
            return self.send_reply(check_str[:-1], conn)
        else:
            return True

    def command_thread(self, conn, addr):
        self.logger.info("Received connection from address: {}:{}".format(*addr))

        # Welcome message
        welcome_msg = str.encode(
            "\n".join(["Welcome to the LIFX process server.", "Type 'help' for a list of commands.\n\n"])
        )
        self.conn_send(conn, welcome_msg + self.prompt)

        loop_active = True
        while loop_active:
            try:
                cmd_bytes = conn.recv(1024)
            except BrokenPipeError:
                cmd_bytes = b""

            if not len(cmd_bytes):
                loop_active = False
                conn.close()

            else:
                command = cmd_bytes.decode().rstrip("\n")
                # telnet adds a carraige return to commands
                command = command.rstrip("\r")
                loop_active = self.run_command(command, conn, addr)

        self.logger.info("Closing connection to address: {}:{}".format(*addr))

    def conn_send(self, conn, send_bytes):
        try:
            conn.send(send_bytes)
            return True
        except BrokenPipeError:
            return False

    def help_display(self, conn):
        # TODO power and cmap
        help_str = "\n".join(
            [
                "Commands:",
                "help            Print the commands.",
                "exit            Quit the client.",
                "check           Check running processes.",
                "devices         List available devices.",
                "groups          List available device groups.",
                "killall         Kill all running processes.",
                "list            List all processes.",
                "off             Turn all lights on the network off.",
                "on              Turn all lights on the network on.",
                "reload          Reload the process configuration file.",
                "restart <proc>  Restart a process from the list of processes.",
                "start <proc>    Start a process from the list of processes.",
                "stop <proc>     Stop a running process.",
            ]
        )
        return self.send_reply(help_str, conn)

    def killall(self, conn):
        while len(self.running_procs):
            proc_name = list(self.running_procs.keys()).pop()
            proc_spr = self.running_procs.pop(proc_name)["proc"]
            proc_spr.terminate()
        return self.send_reply("Killing all running processes.", conn, log_function=self.logger.info)

    def list_cmaps(self, conn):
        cmap_list_str = 'Available color maps (append "_r" for reverse order).\n'
        cmap_list_str += "\n".join(sorted([cmap for cmap in self.cmap_names if cmap[-2:] != "_r"]))
        return self.send_reply(cmap_list_str, conn)

    def list_devices(self, conn):
        if len(self.device_manager.devices):
            device_list_str = "Available devices:\n"
            device_list_str += "\n".join(sorted(self.device_manager.devices.keys()))
            return self.send_reply(device_list_str, conn)
        else:
            return self.send_reply("No devices available.", conn)

    def list_groups(self, conn):
        if len(self.device_manager.groups):
            device_list_str = "Available device groups:\n"
            device_list_str += "\n".join(sorted(self.device_manager.groups.keys()))
            return self.send_reply(device_list_str, conn)
        else:
            return self.send_reply("No device groups available.", conn)

    def list_proc(self, conn):
        """
        List processes.
        """
        avail_procs = []
        for proc in self.avail_procs:
            if proc not in self.running_procs:
                avail_procs.append(proc)

        proc_list_str = ""
        if len(avail_procs):
            proc_list_str += "Available processes:\n"
            for proc in avail_procs:
                if "filename" not in self.avail_procs[proc]:
                    msg = "Missing 'filename' field for process '{}'".format(proc)
                    self.logger.error(msg)
                    continue

                proc_fname = self.avail_procs[proc]["filename"]
                proc_list_str += f"{proc}: {proc_fname}\n"

            if len(self.running_procs):
                proc_list_str += "\n"

        if len(self.running_procs):
            # Check if there are running processes not in the available processes
            # this can happen if the configuration was reloaded.
            orphaned_procs = []
            for proc in self.running_procs:
                if proc not in self.avail_procs:
                    orphaned_procs.append(proc)

            # terminate orphaned processes
            if len(orphaned_procs):
                proc_list_str += "Orphaned processes killed:\n"
            for proc in orphaned_procs:
                process = self.running_procs.pop(proc)["proc"]
                process.terminate()
                proc_list_str += "{}\n".format(proc)

        if len(self.running_procs):
            proc_list_str += "Running processes:\n"
            for proc in self.running_procs:
                if "filename" not in self.avail_procs[proc]:
                    msg = f"Missing 'filename' field for process {proc!r}"
                    self.logger.error(msg)
                    continue

                proc_fname = self.avail_procs[proc]["filename"]
                proc_list_str += f"{proc}: {proc_fname}\n"

        # strip the last endline (the prompt has one)
        return self.send_reply(proc_list_str[:-1], conn)

    def loop(self):
        """
        Get new clients and run command threads
        """
        try:
            while True:
                conn, addr = self.sock.accept()
                client_handler = Thread(target=self.command_thread, args=(conn, addr))
                client_handler.daemon = True
                client_handler.start()

        # Shutdown procedures
        except OSError:
            # Gracefully handle shutdown commands from inside the thread
            sys.exit()
        except KeyboardInterrupt:
            sys.exit()

    def reload_conf(self, conn=None, raise_err=False):
        if os.path.exists(self.avail_proc_yaml_file):
            with open(self.avail_proc_yaml_file) as f:
                self.avail_procs = yaml.safe_load(f)

            if "PROC_DIR" in self.avail_procs:
                self.avail_proc_dir = self.avail_procs.pop("PROC_DIR")
                msg = "Process configuration reloaded."
                log_function = self.logger.info
            else:
                msg = "Invalid process configuration: PROC_DIR missing."
                log_function = self.logger.error
                if raise_err:
                    raise LIFXProcessConfigError(msg)

        else:
            self.avail_procs = {}
            self.avail_proc_dir = ""
            msg = f"Configuration file not found: {self.avail_proc_yaml_file}"
            log_function = self.logger.error
            if raise_err:
                raise LIFXProcessConfigError(msg)
            else:
                log_function("No available processes.")

        if conn is not None:
            return self.send_reply(msg, conn, log_function=log_function)
        else:
            return True

    def run_command(self, command, conn, addr, interactive=True):
        """
        Run a command.

        Command list:
            help
            check
            cmap
            color
            devices
            groups
            killall
            list
            off
            on
            quit
            power
            reload
            restart
            start
            stop
        """
        # basic prompt
        if command == "":
            return self.conn_send(conn, self.prompt)

        elif command == "shutdown":
            if addr[0] != "127.0.0.1":
                return self.send_reply("Server can only be quit locally.", conn)

            running_proc_names = list(self.running_procs.keys())
            for proc_name in running_proc_names:
                proc_spr = self.running_procs.pop(proc_name)["proc"]
                proc_spr.terminate()

            self.send_reply("Shutting down LIFX process server.", conn, log_function=self.logger.info)

            # Not the cleanest exit, but works
            conn.close()
            self.sock.shutdown(socket.SHUT_RDWR)
            self.sock.close()

            return False

        elif command == "exit":
            self.send_reply("Exiting server.", conn)
            conn.close()
            return False

        elif command == "help":
            return self.help_display(conn)

        elif command == "check":
            return self.check_running_procs(conn)

        elif command == "cmap":
            return self.list_cmaps(conn)

        elif command == "devices":
            return self.list_devices(conn)

        elif command == "groups":
            return self.list_groups(conn)

        elif command == "killall":
            return self.killall(conn)

        elif command == "list":
            self.check_running_procs(conn, False)
            return self.list_proc(conn)

        elif command == "off":
            running_proc_names = list(self.running_procs.keys())
            for proc_name in running_proc_names:
                proc_spr = self.running_procs.pop(proc_name)["proc"]
                proc_spr.terminate()

            # retry in case there are some finicky lights
            for i in range(5):
                self.device_manager.set_power(False, 0)
            return self.send_reply("All LIFX lights off.", conn)

        elif command == "on":
            # retry in case there are some finicky lights
            for i in range(5):
                self.device_manager.set_power(True, 0)
            return self.send_reply("All LIFX lights on.", conn)

        elif command == "reload":
            return self.reload_conf(conn)

        else:
            return self.run_command_with_args(command, conn, interactive)

    def run_command_with_args(self, command, conn, interactive=True):
        """
        Run a command with arguments.
        """
        cmd_list = command.split()

        if cmd_list[0] == "api":
            return self.run_command(" ".join(cmd_list[1:]), conn, "", False)

        elif cmd_list[0] == "restart":
            return self.send_reply(self.restart_proc(cmd_list[1:], interactive), conn, interactive)

        elif cmd_list[0] == "start":
            return self.send_reply(self.start_proc(cmd_list[1:], interactive), conn, interactive)

        elif cmd_list[0] == "stop":
            if len(cmd_list) == 2:
                return self.send_reply(self.stop_proc(cmd_list[1], interactive), conn, interactive)
            else:
                return self.send_reply("No process to stop.", conn)

        elif cmd_list[0] == "cmap":
            if len(cmd_list) == 3 or len(cmd_list) == 4:
                dev_name = cmd_list[1]
                cmap_name = cmd_list[2]

                if len(cmd_list) == 4:
                    try:
                        duration = 1000 * int(cmd_list[3])
                    except ValueError:
                        return self.send_reply("Invalid duration.", conn)
                else:
                    duration = 0

                return self.send_reply(self.set_cmap(dev_name, cmap_name, duration), conn)

            elif len(cmd_list) > 4:
                return self.send_reply("Too many arguments.", conn)
            else:
                return self.send_reply("Missing arguments.", conn)

        elif cmd_list[0] == "color":
            if len(cmd_list) == 6 or len(cmd_list) == 7:
                dev_name = cmd_list[1]
                try:
                    hue = float(cmd_list[2])
                    sat = float(cmd_list[3])
                    brightness = float(cmd_list[4])
                    kelvin = int(cmd_list[5])
                except ValueError:
                    return self.send_reply("Invalid HSBK values.", conn)
                hsbk = (hue, sat, brightness, kelvin)

                if len(cmd_list) == 7:
                    try:
                        duration = 1000 * int(cmd_list[6])
                    except ValueError:
                        return self.send_reply("Invalid duration.", conn)
                else:
                    duration = 0

                return self.send_reply(self.set_color(dev_name, hsbk, duration), conn)
            elif len(cmd_list) > 7:
                return self.send_reply("Too many arguments.", conn)
            else:
                return self.send_reply("Missing arguments.", conn)

        elif cmd_list[0] == "power":
            if 2 <= len(cmd_list) <= 4:
                dev_name = cmd_list[1]
                if len(cmd_list) > 2:
                    power_state = cmd_list[2]
                else:
                    power_state = ""

                if len(cmd_list) == 4:
                    try:
                        duration = 1000 * int(cmd_list[3])
                    except ValueError:
                        return self.send_reply("Invalid duration.", conn)
                else:
                    duration = 0

                power_str = self.set_power_state(dev_name, power_state, duration, interactive)
                return self.send_reply(power_str, conn, interactive)

            elif len(cmd_list) > 4:
                return self.send_reply("Too many arguments.", conn)
            else:
                return self.send_reply("Missing arguments.", conn)

        else:
            return self.send_reply("Invalid command.", conn)

    def set_cmap(self, device_name, cmap_name, duration=0):
        cmap_name = cmap_name.replace("-", "_")
        if cmap_name not in self.cmap_names:
            return f"Invalid color map: {cmap_name}"
        cmap = cm.get_cmap(cmap_name)

        if device_name in self.device_manager.groups:
            dev_name_list = self.device_manager.get_group_devices(device_name)

            n_bulbs = 0
            for name in dev_name_list:
                n_bulbs += self.device_manager.devices[name].device_type == "bulb"

            # Set the bulbs
            bulb_colors = np.linspace(0, 1, n_bulbs)
            bulb_colors += random()
            bulb_colors %= 1.0
            shuffle(bulb_colors)

            hsbk_list = [rgba2hsbk(cmap(col), WHITE_KELVIN) for col in bulb_colors]
            for name in dev_name_list:
                device = self.device_manager.devices[name]
                if device.device_type == "bulb":
                    hsbk = hsbk_list.pop()
                    device.set_color(hsbk, duration)
                elif device.device_type == "multizone":
                    device.set_cmap(cmap_name, duration)

            return f"Device group {device_name} color map is {cmap_name}."

        if device_name in self.device_manager.devices:
            device = self.device_manager.devices[device_name]
            if device.device_type == "multizone":
                device.set_cmap(cmap_name, duration)
                return f"Device {device_name} color map is {cmap_name}."
            else:
                hsbk = rgba2hsbk(cmap(random()), WHITE_KELVIN)
                return self.set_color(device_name, hsbk, duration)
        else:
            return "Device {device_name} not in device list."

    def set_color(self, device_name, hsbk, duration=0):
        hue, sat, brightness, kelvin = hsbk

        # validate responses
        # hue gets
        if hue < 0 or hue > 360:
            return "Hue must be between 0 and 360."
        if sat < 0 or sat > 1:
            return "Saturation must be between 0 and 1."
        if brightness < 0 or brightness > 1:
            return "Brightness must be between 0 and 1."
        if kelvin < 2500 or kelvin > 9000:
            return "Kelvin must be between 2500 and 9000."

        # color parameters for response message
        color_param_str = f"Hue: {hue}\n"
        color_param_str += f"Saturation: {sat}\n"
        color_param_str += f"Brightness: {brightness}\n"
        color_param_str += f"Kelvin: {kelvin}"

        if device_name in self.device_manager.groups:
            for dev_name, dev_type in self.device_manager.groups[device_name]:
                self.set_color(dev_name, hsbk, duration)
            response = f"Device group {device_name} color parameters:\n"
            response += color_param_str
            return response

        if device_name in self.device_manager.devices:
            device = self.device_manager.devices[device_name]
            device.set_color(hsbk, duration)
            response = f"Device {device_name} color parameters:\n"
            response += color_param_str
            return response
        else:
            return f"Device {device_name} not in device list."

    def set_power_state(self, device_name, power_state, duration=0, interactive=True):
        power_state_dict = {"on": True, "off": False, "": None}
        if power_state not in power_state_dict:
            if interactive:
                return f"Invalid power state: {power_state}"
            else:
                return "0"

        if power_state_dict[power_state] is None:
            if interactive:
                return "Cannot query."
            else:
                return "0"

        if device_name in self.device_manager.groups:
            for dev_name, dev_type in self.device_manager.groups[device_name]:
                self.set_power_state(dev_name, power_state, duration)

            if interactive:
                return f"Device group {device_name} set {power_state}."
            else:
                return str(int(power_state_dict[power_state]))

        if device_name in self.device_manager.devices:
            state = power_state_dict[power_state]
            device = self.device_manager.devices[device_name]
            device.set_power(state, duration)

            if interactive:
                return f"Device {device_name} set {power_state}."
            else:
                return str(int(power_state_dict[power_state]))
        else:
            if interactive:
                return f"Device {device_name} not in device list."
            else:
                return "0"

    def send_reply(self, reply_str, conn, interactive=True, log_function=None):
        if log_function is not None and interactive:
            log_function(reply_str)
        reply_bytes = str.encode(reply_str + interactive * "\n")

        if interactive:
            reply_bytes += self.prompt

        return self.conn_send(conn, reply_bytes)

    def restart_proc(self, proc_args, interactive=True):
        self.stop_proc(proc_args[0])
        return self.start_proc(proc_args, interactive).replace("start", "restart")

    def start_proc(self, proc_args, interactive=True):
        if len(proc_args):
            proc_name = proc_args.pop(0)
        else:
            if interactive:
                return "No process to start."
            else:
                return "0"

        # don't start a process if already running
        if proc_name in self.running_procs:
            if interactive:
                return f"Process {proc_name} already running."
            else:
                return "1"

        if proc_name not in self.avail_procs:
            if interactive:
                return f"Process {proc_name} not available."
            else:
                return "0"

        for device in self.avail_procs[proc_name].get("devices", []):
            for run_proc in self.running_procs:
                if device in self.running_procs[run_proc].get("devices", []):
                    if interactive:
                        return f"Process {proc_name} conflicts with {run_proc}."
                    else:
                        return "0"

        # if script is not an abspath, it's in a directory
        if "filename" not in self.avail_procs[proc_name]:
            msg = f"Missing 'filename' field for process {proc_name!r}"
            self.logger.error(msg)
            return msg

        proc_script = self.avail_procs[proc_name]["filename"]
        if proc_script[0] != "/":
            proc_script = os.path.join(self.avail_proc_dir, proc_script)

        if not os.path.exists(proc_script):
            msg = f"Can't start script {proc_name}. File {proc_script!r} does not exist."
            self.logger.error(msg)
            return msg

        cmd_list = [proc_script] + proc_args
        if proc_script.endswith(".py"):
            cmd_list.insert(0, sys.executable)

        # ongoing processes get instantly put in the running proccess queue
        if self.avail_procs[proc_name].get("ongoing", False):
            self.running_procs[proc_name] = {
                "proc": spr.Popen(cmd_list, stdout=spr.PIPE, stderr=spr.PIPE),
                "devices": self.avail_procs[proc_name].get("devices", [])[:],
            }
            msg = f"Successfully started process {proc_name}."
            self.logger.info(msg)
            if interactive:
                return msg
            else:
                return "1"
        else:  # one shot processes run quickly and exit
            oneshot = spr.Popen(cmd_list, stdout=spr.PIPE, stderr=spr.PIPE)
            stdout, stderr = oneshot.communicate()
            status_str = ""
            if len(stdout):
                stdout_str = bytes.decode(stdout)
                status_str += f"{proc_name} stdout:\n{stdout_str}\n"
            if len(stderr):
                stderr_str = bytes.decode(stderr)
                status_str += f"{proc_name} stderr:\n{stderr_str}\n"
            if not len(status_str):
                status_str = f"Process {proc_name} exited successfully."

            self.logger.info(status_str)
            if interactive:
                return status_str
            else:
                return "0"

    def stop_proc(self, proc_name, interactive=True):
        # verify that the process is already running
        if proc_name not in self.running_procs:
            if interactive:
                return f"Process {proc_name} is not running."
            else:
                return "0"

        proc_spr = self.running_procs.pop(proc_name)["proc"]
        proc_spr.terminate()
        msg = f"Successfully stopped process {proc_name}."
        self.logger.info(msg)

        if interactive:
            return f"Successfully stopped process {proc_name}."
        else:
            return "0"


if __name__ == "__main__":
    avail_proc_filename = os.path.join(os.environ["HOME"], ".lifx", "processes.yaml")
    server = LIFXProcessServer(avail_proc_filename)
    server.loop()
