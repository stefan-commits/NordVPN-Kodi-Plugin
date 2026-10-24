# SPDX-License-Identifier: GPL-3.0-or-later
"""Kodi program entry point; all network operations belong to NordVPN."""
import sys
import threading
from pathlib import Path

import xbmc
import xbmcaddon
import xbmcgui

from resources.lib.nordvpn import Client, NordError, names, target
from resources.lib.tokenfile import ensure_token_file, read_token


class App:
    def __init__(self):
        self.addon = xbmcaddon.Addon()
        self.dialog = xbmcgui.Dialog()
        self.monitor = xbmc.Monitor()
        self.client = self.make_client()
        self.token_path = Path(__file__).resolve().parent / 'access_token.txt'

    def make_client(self):
        return Client(self.addon.getSetting('cli_path') or 'nordvpn',
                      flatpak_host=self.addon.getSetting('flatpak_host') == 'true')

    def choose(self, title, choices):
        return self.dialog.select(title, choices)

    def input(self, title, hidden=False):
        return self.dialog.input(title, type=xbmcgui.INPUT_ALPHANUM,
                                 option=xbmcgui.ALPHANUM_HIDE_INPUT if hidden else 0).strip()

    def execute(self, function, *args, show=True, **kwargs):
        # Worker keeps the Kodi dialog responsive during daemon/network waits.
        result = []
        errors = []
        def work():
            try:
                result.append(function(*args, **kwargs))
            except Exception as exc:
                # Never display arbitrary exception strings: they can contain argv/token.
                errors.append(str(exc) if isinstance(exc, NordError) else 'Unexpected command error. Check the NordVPN installation.')
        progress = xbmcgui.DialogProgressBG()
        progress.create('NordVPN', 'Waiting for NordVPN…')
        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        try:
            while worker.is_alive():
                if self.monitor.waitForAbort(0.1):
                    return None
        finally:
            progress.close()
        if errors:
            self.dialog.ok('NordVPN', errors[0])
            return None
        output = result[0]
        if show and isinstance(output, str):
            self.dialog.textviewer('NordVPN', output)
        return output

    def command(self, *args, **kwargs):
        return self.execute(self.client.run, *args, **kwargs)

    def location(self, group=''):
        countries = self.execute(self.client.locations, show=False)
        if not countries:
            return
        choice = self.choose('Country', [c.replace('_', ' ') for c in countries])
        if choice < 0:
            return
        country = countries[choice]
        cities = self.execute(self.client.locations, country, show=False)
        if cities is None:
            return
        choice = self.choose('City in ' + country.replace('_', ' '), ['Fastest available'] + [c.replace('_', ' ') for c in cities])
        if choice >= 0:
            self.execute(self.client.connect, country, cities[choice - 1] if choice else '', group)

    def groups(self):
        groups = self.command('groups', show=False)
        if groups is None:
            return
        groups = names(groups)
        choice = self.choose('Server group', [g.replace('_', ' ') for g in groups]) if groups else -1
        if choice < 0:
            return
        group = groups[choice]
        choice = self.choose('Location', ['Fastest available', 'Choose country and city'])
        if choice == 0:
            self.execute(self.client.connect, group=group)
        elif choice == 1:
            self.location(group)

    def login(self):
        ensure_token_file(self.token_path)
        token = read_token(self.token_path)
        try:
            self.execute(self.client.login, token)
        finally:
            token = None

    def logout(self):
        if self.dialog.yesno('NordVPN', 'Log out of NordVPN? Your access token will remain valid and the token file will be kept for future login.'):
            self.execute(self.client.logout)

    def settings(self):
        toggles = [('Kill Switch', 'killswitch'), ('Real-time protection', 'protection'),
                   ('Notifications', 'notify'), ('Post-quantum VPN', 'pq'),
                   ('Encrypted Client Hello', 'ech'), ('Meshnet', 'meshnet')]
        choices = ['Show current settings', 'VPN protocol', 'Auto-connect', 'Custom DNS'] + [x[0] for x in toggles]
        while not self.monitor.abortRequested():
            choice = self.choose('NordVPN settings', choices)
            if choice < 0:
                return
            if choice == 0:
                self.command('settings')
            elif choice == 1:
                options = ['nordlynx', 'openvpn_udp', 'openvpn_tcp', 'nordwhisper']
                index = self.choose('VPN protocol', options)
                if index >= 0:
                    self.command('set', 'protocol', options[index])
            elif choice == 2:
                index = self.choose('Auto-connect', ['Off', 'Fastest available', 'Country / city / group'])
                if index == 0:
                    self.command('set', 'autoconnect', 'off')
                elif index == 1:
                    self.command('set', 'autoconnect', 'on')
                elif index == 2:
                    country = self.input('Country or group (e.g. United_States)')
                    if country:
                        city = self.input('City (optional; cancel for any city)')
                        self.command('set', 'autoconnect', 'on', *[target(x) for x in (country, city) if x])
            elif choice == 3:
                value = self.input('DNS IP addresses separated by spaces, or off')
                if value:
                    self.execute(self.client.dns, value)
            else:
                label, setting = toggles[choice - 4]
                index = self.choose(label, ['On', 'Off'])
                if index >= 0:
                    if setting == 'killswitch' and index == 0 and not self.dialog.yesno('Kill Switch', 'Internet access can be blocked while the VPN is disconnected. Enable Kill Switch?'):
                        continue
                    self.command('set', setting, 'on' if index == 0 else 'off')

    def allowlist(self):
        while not self.monitor.abortRequested():
            choice = self.choose('Allowlist', ['Show settings / allowlist', 'Add entry', 'Remove entry', 'Remove all entries'])
            if choice < 0:
                return
            if choice == 0:
                self.command('settings')
                continue
            if choice == 3:
                if self.dialog.yesno('Allowlist', 'Remove all allowlisted ports and subnets?'):
                    self.command('allowlist', 'remove', 'all')
                continue
            kind = self.choose('Entry type', ['Port', 'Port range', 'Subnet'])
            if kind < 0:
                continue
            value = self.input(['Port number', 'Start and end port separated by a space', 'Subnet (e.g. 192.168.1.0/24)'][kind])
            if not value:
                continue
            protocol = ''
            if kind != 2:
                index = self.choose('Protocol', ['Both', 'TCP', 'UDP'])
                if index < 0:
                    continue
                protocol = ['', 'TCP', 'UDP'][index]
            self.execute(self.client.allowlist, 'add' if choice == 1 else 'remove', ['port', 'ports', 'subnet'][kind], value, protocol)

    def advanced(self):
        # Installed CLI help is authoritative for settings added after this manual.
        choice = self.choose('More controls', ['Installed CLI help', 'Available settings', 'Set another option', 'Meshnet peers', 'Connect to Meshnet peer', 'Rate last connection', 'NordVPN version'])
        if choice == 0:
            self.command('--help')
        elif choice == 1:
            self.command('set', '--help')
        elif choice == 2:
            key = self.input('Setting name from NordVPN set help')
            if key:
                key = target(key)
                self.command('set', key, '--help')
                value = self.input('Value(s), separated by spaces; cancel to return')
                if value:
                    self.command('set', key, *[target(x) for x in value.split()])
        elif choice == 3:
            self.command('meshnet', 'peer', 'list')
        elif choice == 4:
            peer = self.input('Peer Nord hostname, nickname, or IP address')
            if peer:
                self.command('meshnet', 'peer', 'connect', target(peer))
        elif choice == 5:
            rating = self.choose('Rate last connection', ['1 — Poor', '2', '3', '4', '5 — Excellent'])
            if rating >= 0:
                self.command('rate', str(rating + 1))
        elif choice == 6:
            self.command('version')

    def run(self):
        if not sys.platform.startswith('linux'):
            self.dialog.ok('NordVPN', 'This add-on requires Kodi on Linux and the installed NordVPN Linux CLI.')
            return
        try:
            ensure_token_file(self.token_path)
        except NordError as exc:
            self.dialog.ok('NordVPN', str(exc))
        actions = [('Status', lambda: self.command('status')),
                   ('Quick connect', lambda: self.execute(self.client.connect)),
                   ('Connect by country / city', self.location), ('Connect by server group', self.groups),
                   ('Connect to a specific server', self.server), ('Disconnect', lambda: self.command('disconnect')),
                   ('Log in from token file', self.login), ('Log out', self.logout),
                   ('Token file location', lambda: self.dialog.textviewer('NordVPN token file', str(self.token_path) + '\n\nPaste your access token into this file on one line, without quotes. Save it, then select Log in from token file.')),
                   ('Account', lambda: self.command('account')), ('NordVPN settings', self.settings),
                   ('Allowlist', self.allowlist), ('More controls / CLI help', self.advanced),
                   ('Add-on settings', self.configure)]
        while not self.monitor.abortRequested():
            choice = self.choose('NordVPN', [label for label, _ in actions])
            if choice < 0:
                break
            try:
                actions[choice][1]()
            except NordError as exc:
                self.dialog.ok('NordVPN', str(exc))

    def server(self):
        server = self.input('Server name (e.g. us1234)')
        if server:
            self.execute(self.client.connect, server)

    def configure(self):
        self.addon.openSettings()
        self.client = self.make_client()


if __name__ == '__main__':
    App().run()
