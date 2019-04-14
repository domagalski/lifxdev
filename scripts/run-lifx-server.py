#!/usr/bin/env python3

import os
import sys
import signal
import socket
import subprocess as spr
from random import random
from threading import Thread

import yaml
from matplotlib import cm

from lifxdev import DeviceManager, rgba2hsbk

WHITE_KELVIN = 5000

class LIFXProcessServer(object):
    def __init__(self, avail_proc_yaml_file):
        self.avail_proc_yaml_file = avail_proc_yaml_file
        self.reload_conf()

        # port to listen on
        self.port = 16384
        # Empty dictionary
        self.running_procs = {}

        # initialize the socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('', self.port))
        self.sock.listen(5)

        # prompt for the client
        self.prompt = b'LIFX> '

        self.device_manager = DeviceManager()
        self.device_manager.load_config(do_init_socket=True)

        # Color map names
        self.cmap_names = list(cm.cmap_d.keys())
        self.cmap_names += list(cm.cmaps_listed.keys())
        self.cmap_names = list(set(self.cmap_names))

    def check_running_procs(self, conn, send_reply=True):
        running_proc_names = list(self.running_procs.keys())

        check_str = ''
        for proc_name in running_proc_names:
            # check the return code of each process
            proc = self.running_procs[proc_name]['proc']
            status_code = proc.poll()

            # None means the process is still running
            if status_code is None:
                continue

            # if the process has exited without error, quietly remove
            proc = self.running_procs.pop(proc_name)['proc']
            if status_code:
                stdout, stderr = proc.communicate()
                if len(stdout):
                    check_str += '{} stdout:\n{}\n'.format(proc_name, bytes.decode(stdout))
                if len(stderr):
                    check_str += '{} stderr:\n{}\n'.format(proc_name, bytes.decode(stderr))

        if not len(check_str) and send_reply:
            check_str = 'No processes with errors.\n'

        if len(check_str):
            self.send_reply(check_str[:-1], conn)

    def command_thread(self, conn, addr):
        # Welcome message
        welcome_msg = str.encode('\n'.join([
            'Welcome to the LIFX process server.',
            'Type \'help\' for a list of commands.\n\n',
            ]))
        conn.send(welcome_msg + self.prompt)

        loop_active = True
        while loop_active:
            cmd_bytes = conn.recv(1024)
            if not len(cmd_bytes):
                loop_active = False
                conn.close()

            # Only continue if ascii command
            elif cmd_bytes.isascii():
                command = cmd_bytes.decode().rstrip('\n')
                # telnet adds a carraige return to commands
                command = command.rstrip('\r')
                loop_active = self.run_command(command, conn, addr)

    def help_display(self, conn):
        # TODO power and cmap
        help_str = '\n'.join([
                'Commands:',
                'help            Print the commands.',
                'exit            Quit the client.',
                'check           Check running processes.',
                'devices         List available devices.',
                'groups          List available device groups.',
                'list            List all processes.',
                'off             Turn all lights on the network off.',
                'on              Turn all lights on the network on.',
                'reload          Reload the process configuration file.',
                'restart <proc>  Restart a process from the list of processes.',
                'start <proc>    Start a process from the list of processes.',
                'stop <proc>     Stop a running process.',
                ])
        self.send_reply(help_str, conn)

    def list_cmaps(self, conn):
        cmap_list_str = 'Available color maps (append "_r" for reverse order).\n'
        cmap_list_str += '\n'.join(sorted([cmap for cmap in self.cmap_names if cmap[-2:] != '_r']))
        self.send_reply(cmap_list_str, conn)

    def list_devices(self, conn):
        if len(self.device_manager.devices):
            device_list_str = 'Available devices:\n'
            device_list_str += '\n'.join(sorted(self.device_manager.devices.keys()))
            self.send_reply(device_list_str, conn)
        else:
            self.send_reply('No devices available.', conn)

    def list_groups(self, conn):
        if len(self.device_manager.groups):
            device_list_str = 'Available device groups:\n'
            device_list_str += '\n'.join(sorted(self.device_manager.groups.keys()))
            self.send_reply(device_list_str, conn)
        else:
            self.send_reply('No device groups available.', conn)

    def list_proc(self, conn):
        """
        List processes.
        """
        avail_procs = []
        for proc in self.avail_procs:
            if proc not in self.running_procs:
                avail_procs.append(proc)

        proc_list_str = ''
        if len(avail_procs):
            proc_list_str += 'Available processes:\n'
            for proc in avail_procs:
                proc_list_str += '{}: {}\n'.format(proc, self.avail_procs[proc]["filename"])

            if len(self.running_procs):
                proc_list_str += '\n'

        if len(self.running_procs):
            # Check if there are running processes not in the available processes
            # this can happen if the configuration was reloaded.
            orphaned_procs = []
            for proc in self.running_procs:
                if proc not in self.avail_procs:
                    orphaned_procs.append(proc)

            # terminate orphaned processes
            if len(orphaned_procs):
                proc_list_str += 'Orphaned processes killed:\n'
            for proc in orphaned_procs:
                process = self.running_procs.pop(proc)['proc']
                process.terminate()
                proc_list_str += '{}\n'.format(proc)

        if len(self.running_procs):
            proc_list_str += 'Running processes:\n'
            for proc in self.running_procs:
                proc_list_str += '{}: {}\n'.format(proc, self.avail_procs[proc]["filename"])

        # strip the last endline (the prompt has one)
        self.send_reply(proc_list_str[:-1], conn)

    def loop(self):
        """
        Get new clients and run command threads
        """
        try:
            while True:
                conn, addr = self.sock.accept()
                client_handler = Thread(
                        target=self.command_thread,
                        args=(conn, addr)
                        )
                client_handler.daemon = True
                client_handler.start()

        # Shutdown procedures
        except OSError:
            # Gracefully handle shutdown commands from inside the thread
            sys.exit()
        except KeyboardInterrupt:
            sys.exit()

    def reload_conf(self, conn=None):
        with open(self.avail_proc_yaml_file) as f:
            self.avail_procs = yaml.load(f)
        self.avail_proc_dir = self.avail_procs.pop('PROC_DIR')

        if conn is not None:
            self.send_reply('Process configuration reloaded.', conn)

    def run_command(self, command, conn, addr):
        """
        Run a command.

        Command list:
            help
            check
            list
            off
            on
            quit
            reload
            restart
            start
            stop
        """
        # basic prompt
        if command == '':
            conn.send(self.prompt)

        elif command == 'shutdown':
            if addr[0] != '127.0.0.1':
                self.send_reply('Server can only be quit locally.', conn)
                return True

            running_proc_names = list(self.running_procs.keys())
            for proc_name in running_proc_names:
                proc_spr = self.running_procs.pop(proc_name)['proc']
                proc_spr.terminate()

            self.send_reply('Shutting down LIFX process server.', conn)

            # Not the cleanest exit, but works
            conn.close()
            self.sock.shutdown(socket.SHUT_RDWR)
            self.sock.close()

            return False

        elif command == 'exit':
            self.send_reply('Exiting server.', conn)
            conn.close()
            return False

        elif command == 'help':
            self.help_display(conn)

        elif command == 'check':
            self.check_running_procs(conn)

        elif command == 'cmap':
            self.list_cmaps(conn)

        elif command == 'devices':
            self.list_devices(conn)

        elif command == 'groups':
            self.list_groups(conn)

        elif command == 'list':
            self.check_running_procs(conn, False)
            self.list_proc(conn)

        elif command == 'off':
            running_proc_names = list(self.running_procs.keys())
            for proc_name in running_proc_names:
                proc_spr = self.running_procs.pop(proc_name)['proc']
                proc_spr.terminate()

            # retry in case there are some finicky lights
            for i in range(5):
                self.device_manager.set_power(False, 0)
            self.send_reply('All LIFX lights off.', conn)

        elif command == 'on':
            # retry in case there are some finicky lights
            for i in range(5):
                self.device_manager.set_power(True, 0)
            self.send_reply('All LIFX lights on.', conn)

        elif command == 'reload':
            self.reload_conf(conn)

        else:
            self.run_command_with_args(command, conn)

        # always return true unless the quit function is received
        return True

    def run_command_with_args(self, command, conn):
        """
        Run a command with arguments.
        """
        cmd_list = command.split()

        if cmd_list[0] == 'restart':
            self.send_reply(self.restart_proc(cmd_list[1:]), conn)

        elif cmd_list[0] == 'start':
            self.send_reply(self.start_proc(cmd_list[1:]), conn)

        elif cmd_list[0] == 'stop':
            if len(cmd_list) == 2:
                self.send_reply(self.stop_proc(cmd_list[1]), conn)
            else:
                self.send_reply('No process to stop.', conn)

        elif cmd_list[0] == 'cmap':
            if len(cmd_list) == 3 or len(cmd_list) == 4:
                dev_name = cmd_list[1]
                cmap_name = cmd_list[2]

                if len(cmd_list) == 4:
                    try:
                        duration = 1000*int(cmd_list[3])
                    except ValueError:
                        self.send_reply('Invalid duration.', conn)
                        return
                else:
                    duration = 0

                self.send_reply(self.set_cmap(dev_name, cmap_name, duration), conn)

            elif len(cmd_list) > 4:
                self.send_reply('Too many arguments.', conn)
            else:
                self.send_reply('Missing arguments.', conn)

        elif cmd_list[0] == 'color':
            if len(cmd_list) == 6 or len(cmd_list) == 7:
                dev_name = cmd_list[1]
                try:
                    hue = float(cmd_list[2])
                    sat = float(cmd_list[3])
                    brightness = float(cmd_list[4])
                    kelvin = int(cmd_list[5])
                except ValueError:
                    self.send_reply('Invalid HSBK values.', conn)
                    return
                hsbk = (hue, sat, brightness, kelvin)

                if len(cmd_list) == 7:
                    try:
                        duration = 1000*int(cmd_list[6])
                    except ValueError:
                        self.send_reply('Invalid duration.', conn)
                        return
                else:
                    duration = 0

                self.send_reply(self.set_color(dev_name, hsbk, duration), conn)
            elif len(cmd_list) > 7:
                self.send_reply('Too many arguments.', conn)
            else:
                self.send_reply('Missing arguments.', conn)

        elif cmd_list[0] == 'power':
            if len(cmd_list) == 3 or len(cmd_list) == 4:
                dev_name = cmd_list[1]
                power_state = cmd_list[2]

                if len(cmd_list) == 4:
                    try:
                        duration = 1000*int(cmd_list[3])
                    except ValueError:
                        self.send_reply('Invalid duration.', conn)
                        return
                else:
                    duration = 0

                self.send_reply(self.set_power_state(dev_name, power_state, duration), conn)

            elif len(cmd_list) > 4:
                self.send_reply('Too many arguments.', conn)
            else:
                self.send_reply('Missing arguments.', conn)

        else:
            self.send_reply('Invalid command.', conn)

    def set_cmap(self, device_name, cmap_name, duration=0):
        cmap_name = cmap_name.replace('-', '_')
        if cmap_name not in self.cmap_names:
            return 'Invalid color map: {}'.format(cmap_name)

        if device_name in self.device_manager.groups:
            for dev_name, dev_type in self.device_manager.groups[device_name]:
                self.set_cmap(dev_name, cmap_name, duration)
            return 'Device group {} color map is {}.'.format(device_name, cmap_name)

        if device_name in self.device_manager.devices:
            device = self.device_manager.devices[device_name]
            device.set_power(True, 0)
            if device.device_type == 'multizone':
                device.set_cmap(cmap_name, duration)
                return 'Device {} color map is {}.'.format(device_name, cmap_name)
            else:
                cmap = cm.get_cmap(cmap_name)
                hsbk = rgba2hsbk(cmap(random()), WHITE_KELVIN)
                return self.set_color(device_name, hsbk, duration)
        else:
            return 'Device {} not in device list.'.format(device_name)

    def set_color(self, device_name, hsbk, duration=0):
        hue, sat, brightness, kelvin = hsbk

        # validate responses
        # hue gets
        if hue < 0 or hue > 360:
            return 'Hue must be between 0 and 360.'
        if sat < 0 or sat > 1:
            return 'Saturation must be between 0 and 1.'
        if brightness < 0 or brightness > 1:
            return 'Brightness must be between 0 and 1.'
        if kelvin < 2500 or kelvin > 9000:
            return 'Kelvin must be between 2500 and 9000.'

        # color parameters for response message
        color_param_str = 'Hue: {}\n'.format(hue)
        color_param_str += 'Saturation: {}\n'.format(sat)
        color_param_str += 'Brightness: {}\n'.format(brightness)
        color_param_str += 'Kelvin: {}'.format(kelvin)

        if device_name in self.device_manager.groups:
            for dev_name, dev_type in self.device_manager.groups[device_name]:
                self.set_color(dev_name, hsbk, duration)
            response = 'Device group {} color parameters:\n'.format(device_name)
            response += color_param_str
            return response

        if device_name in self.device_manager.devices:
            device = self.device_manager.devices[device_name]
            device.set_power(True, 0)
            device.set_color(hsbk, duration)
            response = 'Device {} color parameters:\n'.format(device_name)
            response += color_param_str
            return response
        else:
            return 'Device {} not in device list.'.format(device_name)

    def set_power_state(self, device_name, power_state, duration=0):
        power_state_dict = {'on': True, 'off': False}
        if power_state not in power_state_dict:
            return 'Invalid power state: {}'.format(power_state)

        if device_name in self.device_manager.groups:
            for dev_name, dev_type in self.device_manager.groups[device_name]:
                self.set_power_state(dev_name, power_state, duration)
            return 'Device group {} set {}.'.format(device_name, power_state)

        if device_name in self.device_manager.devices:
            state = power_state_dict[power_state]
            device = self.device_manager.devices[device_name]
            device.set_power(state, duration)
            return 'Device {} set {}.'.format(device_name, power_state)
        else:
            return 'Device {} not in device list.'.format(device_name)

    def send_reply(self, reply_str, conn):
        reply_bytes = str.encode(reply_str + '\n')
        reply_bytes += self.prompt
        conn.send(reply_bytes)

    def restart_proc(self, proc_args):
        self.stop_proc(proc_args[0])
        return self.start_proc(proc_args).replace('start', 'restart')

    def start_proc(self, proc_args):
        if len(proc_args):
            proc_name = proc_args.pop(0)
        else:
            return 'No process to start.'

        # don't start a process if already running
        if proc_name in self.running_procs:
            return 'Process {} already running.'.format(proc_name)

        if proc_name not in self.avail_procs:
            return 'Process {} not available.'.format(proc_name)

        for device in self.avail_procs[proc_name]['devices']:
            for run_proc in self.running_procs:
                if device in self.running_procs[run_proc]['devices']:
                    return 'Process {} conflicts with {}.'.format(proc_name, run_proc)

        # if script is not an abspath, it's in a directory
        proc_script = self.avail_procs[proc_name]["filename"]
        if proc_script[0] != '/':
            proc_script = os.path.join(self.avail_proc_dir, proc_script)
        cmd_list = ['python3', proc_script] + proc_args

        # ongoing processes get instantly put in the running proccess queue
        if self.avail_procs[proc_name]['ongoing']:
            self.running_procs[proc_name] = {
                    'proc': spr.Popen(cmd_list, stdout=spr.PIPE, stderr=spr.PIPE),
                    'devices': self.avail_procs[proc_name]['devices'][:]
                    }
            return 'Successfully started process {}.'.format(proc_name)
        else: # one shot processes run quickly and exit
            oneshot = spr.Popen(cmd_list, stdout=spr.PIPE, stderr=spr.PIPE)
            stdout, stderr = oneshot.communicate()
            status_str = ''
            if len(stdout):
                status_str += '{} stdout:\n{}\n'.format(proc_name, bytes.decode(stdout))
            if len(stderr):
                status_str += '{} stderr:\n{}'.format(proc_name, bytes.decode(stderr))
            if not len(status_str):
                status_str = 'Process {} exited successfully.'.format(proc_name)
            return status_str

    def stop_proc(self, proc_name):
        # verify that the process is already running
        if proc_name not in self.running_procs:
            return 'Process {} is not running.'.format(proc_name)

        proc_spr = self.running_procs.pop(proc_name)['proc']
        proc_spr.terminate()
        return 'Successfully stopped process {}.'.format(proc_name)

if __name__ == '__main__':
    avail_proc_filename = os.path.join(os.environ['HOME'], '.lifx/processes.yaml')
    server = LIFXProcessServer(avail_proc_filename)
    server.loop()
