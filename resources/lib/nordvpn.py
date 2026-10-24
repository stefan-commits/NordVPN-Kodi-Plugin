"""Small, shell-free adapter for the installed NordVPN Linux CLI."""
import ipaddress
import os
import re
import subprocess


class NordError(Exception):
    pass


def clean(text):
    return re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text).replace('\r', '\n').strip()


def names(text):
    """CLI locations are whitespace-separated identifiers with underscores."""
    result = []
    for line in clean(text).splitlines():
        if ':' in line or not line.strip():
            continue
        for name in line.split():
            if re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', name) and name not in result:
                result.append(name)
    return sorted(result, key=str.casefold)


def target(value):
    value = value.strip().replace(' ', '_')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,252}', value):
        raise NordError('Enter a country, city, group, or server name; command options are not accepted.')
    return value


class Client:
    def __init__(self, executable='nordvpn', timeout=90, flatpak_host=False):
        self.executable = (executable or 'nordvpn').strip() or 'nordvpn'
        self.timeout = timeout
        self.flatpak_host = flatpak_host

    def run(self, *args, secret=None):
        env = dict(os.environ, LC_ALL='C', LANG='C', NO_COLOR='1', TERM='dumb')
        command = [self.executable] + list(args)
        if self.flatpak_host:
            command = ['flatpak-spawn', '--host', '--watch-bus', '--directory=/',
                       '--env=LC_ALL=C', '--env=LANG=C', '--env=NO_COLOR=1',
                       '--env=TERM=dumb'] + command
        try:
            proc = subprocess.run(
                command, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                universal_newlines=True, errors='replace', env=env,
                timeout=self.timeout, shell=False)
        except subprocess.TimeoutExpired:
            raise NordError('NordVPN did not finish in time. The daemon may still be working; check Status before retrying.') from None
        except FileNotFoundError:
            if self.flatpak_host:
                raise NordError('flatpak-spawn was not found inside Kodi. Host-command mode requires Flatpak Kodi with the flatpak-spawn helper.') from None
            if os.path.exists('/.flatpak-info') or os.environ.get('FLATPAK_ID'):
                raise NordError('Kodi is running inside Flatpak and cannot start the host NordVPN executable. Enable Flatpak host commands in Add-on settings and grant the host-command permission described in the README.') from None
            raise NordError('NordVPN could not be started. Check the executable path and its required Linux loader. For Flatpak Kodi, enable Flatpak host commands in Add-on settings.') from None
        except OSError:
            raise NordError('Cannot execute NordVPN. Check the executable path and the Kodi user’s permissions.') from None
        output = clean(proc.stdout)
        if secret:
            output = output.replace(secret, '[hidden]')
        if proc.returncode:
            if self.flatpak_host:
                output += '\n\nHost-command mode: if access was denied, check the org.freedesktop.Flatpak permission for Kodi. If the executable was not found, check its path on the Debian host.'
            raise NordError(output or 'NordVPN command failed (exit {}).'.format(proc.returncode))
        return output or 'Command completed.'

    def login(self, token):
        token = token.strip()
        if not token or any(c.isspace() for c in token) or token.startswith('-'):
            raise NordError('Enter a valid Nord Account access token without spaces.')
        return self.run('login', '--token', token, secret=token)

    def logout(self):
        # Defaults changed between CLI generations. Inspect capabilities before
        # mutating the session; never retry an unknown flag with bare logout.
        help_text = self.run('logout', '--help')
        flags = set(re.findall(r'(?<![\w-])--([a-z][a-z-]*)(?![\w-])', help_text))
        if 'revoke-token' in flags:
            return self.run('logout', '--revoke-token=false')
        if 'persist-token' in flags:
            return self.run('logout', '--persist-token')
        raise NordError('Logout was not attempted because this CLI’s token behavior could not be determined. Check nordvpn logout --help for supported token options.')

    def connect(self, country='', city='', group=''):
        args = ['connect']
        if group:
            args += ['--group', target(group)]
        args += [target(x) for x in (country, city) if x]
        return self.run(*args)

    def locations(self, country=None):
        return names(self.run('cities', target(country))) if country else names(self.run('countries'))

    def dns(self, value):
        if value.strip().lower() == 'off':
            return self.run('set', 'dns', 'off')
        values = value.replace(',', ' ').split()
        if not 1 <= len(values) <= 3:
            raise NordError('Enter one to three DNS IP addresses, or off.')
        try:
            values = [str(ipaddress.ip_address(v)) for v in values]
        except ValueError:
            raise NordError('A DNS address is invalid.') from None
        return self.run('set', 'dns', *values)

    def allowlist(self, operation, kind, value, protocol=''):
        if operation not in ('add', 'remove'):
            raise NordError('Invalid allowlist operation.')
        if kind == 'subnet':
            try:
                values = [str(ipaddress.ip_network(value.strip(), strict=False))]
            except ValueError:
                raise NordError('Enter a valid subnet, such as 192.168.1.0/24.') from None
        elif kind in ('port', 'ports'):
            values = value.split()
            if len(values) != (1 if kind == 'port' else 2) or any(
                    not v.isdigit() or not 1 <= int(v) <= 65535 for v in values):
                raise NordError('Ports must be between 1 and 65535; a range needs a start and end.')
            if len(values) == 2 and int(values[0]) > int(values[1]):
                raise NordError('The start port must not exceed the end port.')
        else:
            raise NordError('Invalid allowlist type.')
        if protocol not in ('', 'TCP', 'UDP'):
            raise NordError('Invalid protocol.')
        return self.run('allowlist', operation, kind, *values,
                        *(['protocol', protocol] if protocol and kind != 'subnet' else []))
