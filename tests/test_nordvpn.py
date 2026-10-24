import subprocess
import unittest
from unittest.mock import patch

from resources.lib.nordvpn import Client, NordError, names, target


class ClientTests(unittest.TestCase):
    def test_flatpak_host_transport_and_redaction(self):
        with patch('resources.lib.nordvpn.subprocess.run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, 'echo secret-token')
            output = Client(' /usr/bin/nordvpn ', flatpak_host=True).login('secret-token')
            argv = run.call_args.args[0]
            self.assertEqual(argv[:4], ['flatpak-spawn', '--host', '--watch-bus', '--directory=/'])
            self.assertIn('--env=LC_ALL=C', argv)
            self.assertEqual(argv[-4:], ['/usr/bin/nordvpn', 'login', '--token', 'secret-token'])
            self.assertFalse(run.call_args.kwargs['shell'])
            self.assertNotIn('secret-token', output)

    def test_flatpak_missing_helper(self):
        with patch('resources.lib.nordvpn.subprocess.run', side_effect=FileNotFoundError()):
            with self.assertRaisesRegex(NordError, 'flatpak-spawn was not found'):
                Client(flatpak_host=True).run('version')

    def test_flatpak_permission_failure(self):
        with patch('resources.lib.nordvpn.subprocess.run', return_value=subprocess.CompletedProcess([], 1, 'AccessDenied secret-token')):
            with self.assertRaises(NordError) as context:
                Client(flatpak_host=True).login('secret-token')
            self.assertIn('org.freedesktop.Flatpak', str(context.exception))
            self.assertNotIn('secret-token', str(context.exception))

    def run_with(self, method, *args, **kwargs):
        with patch('resources.lib.nordvpn.subprocess.run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, 'Done')
            result = getattr(Client(), method)(*args, **kwargs)
            return run.call_args, result

    def test_shell_free_and_closed_stdin(self):
        call, _ = self.run_with('connect', 'United States', 'New York', 'Double_VPN')
        self.assertEqual(call.args[0], ['nordvpn', 'connect', '--group', 'Double_VPN', 'United_States', 'New_York'])
        self.assertFalse(call.kwargs['shell'])
        self.assertEqual(call.kwargs['stdin'], subprocess.DEVNULL)
        self.assertEqual(call.kwargs['env']['LC_ALL'], 'C')
        self.assertEqual(call.kwargs['timeout'], 90)

    def test_login_redacts_response_and_error(self):
        for code in (0, 1):
            with patch('resources.lib.nordvpn.subprocess.run', return_value=subprocess.CompletedProcess([], code, 'echo secret-token')):
                if code:
                    with self.assertRaises(NordError) as context:
                        Client().login('secret-token')
                    self.assertNotIn('secret-token', str(context.exception))
                else:
                    self.assertEqual(Client().login('secret-token'), 'echo [hidden]')

    def test_logout_modern_and_legacy(self):
        for flatpak in (False, True):
            for flag in ('revoke-token', 'persist-token'):
                with self.subTest(flatpak=flatpak, flag=flag):
                    with patch('resources.lib.nordvpn.subprocess.run') as run:
                        run.side_effect = [
                            subprocess.CompletedProcess([], 0, 'OPTIONS:\n   --' + flag + ' (default: false)'),
                            subprocess.CompletedProcess([], 0, 'Logged out')]
                        Client('/usr/bin/nordvpn', flatpak_host=flatpak).logout()
                        self.assertEqual(run.call_args_list[0].args[0][-3:], ['/usr/bin/nordvpn', 'logout', '--help'])
                        expected = ['/usr/bin/nordvpn', 'logout', '--revoke-token=false' if flag == 'revoke-token' else '--persist-token']
                        self.assertEqual(run.call_args.args[0][-len(expected):], expected)
                        if flatpak:
                            self.assertEqual(run.call_args.args[0][:2], ['flatpak-spawn', '--host'])

    def test_logout_unknown_help_does_not_change_session(self):
        for help_text in ('OPTIONS: --help', 'OPTIONS: --persist-token-other'):
            with patch('resources.lib.nordvpn.subprocess.run', return_value=subprocess.CompletedProcess([], 0, help_text)) as run:
                with self.assertRaisesRegex(NordError, 'Logout was not attempted'):
                    Client().logout()
                self.assertEqual(run.call_count, 1)

    def test_logout_help_failure_does_not_change_session(self):
        with patch('resources.lib.nordvpn.subprocess.run', return_value=subprocess.CompletedProcess([], 1, 'Permission denied')) as run:
            with self.assertRaises(NordError):
                Client().logout()
            self.assertEqual(run.call_count, 1)

    def test_logout_failure_is_not_retried(self):
        with patch('resources.lib.nordvpn.subprocess.run') as run:
            run.side_effect = [subprocess.CompletedProcess([], 0, 'OPTIONS: --revoke-token'),
                               subprocess.CompletedProcess([], 1, 'Logout failed')]
            with self.assertRaises(NordError):
                Client().logout()
            self.assertEqual(run.call_count, 2)

    def test_timeout_does_not_expose_command(self):
        with patch('resources.lib.nordvpn.subprocess.run', side_effect=subprocess.TimeoutExpired(['nordvpn', 'secret-token'], 90)):
            with self.assertRaises(NordError) as context:
                Client().login('secret-token')
            self.assertNotIn('secret-token', str(context.exception))
            self.assertIn('check Status', str(context.exception))

    def test_unavailable_executable(self):
        for error in (FileNotFoundError(), PermissionError()):
            with patch('resources.lib.nordvpn.subprocess.run', side_effect=error):
                with self.assertRaises(NordError):
                    Client().run('status')

    def test_injection_and_option_rejection(self):
        for value in ('--help', 'US; touch /tmp/file', '$(whoami)', 'a\nb', '', '../server'):
            with self.assertRaises(NordError):
                target(value)

    def test_locations(self):
        self.assertEqual(names('\x1b[32mCountries:\x1b[0m\nUnited_States\tCanada\nGermany   Canada\n'), ['Canada', 'Germany', 'United_States'])
        call, _ = self.run_with('locations', 'United States')
        self.assertEqual(call.args[0], ['nordvpn', 'cities', 'United_States'])

    def test_dns(self):
        call, _ = self.run_with('dns', '1.1.1.1, 2606:4700:4700::1111')
        self.assertEqual(call.args[0][-2:], ['1.1.1.1', '2606:4700:4700::1111'])
        for value in ('', 'invalid', '1.1.1.1 --help'):
            with self.assertRaises(NordError):
                Client().dns(value)

    def test_allowlist(self):
        call, _ = self.run_with('allowlist', 'add', 'ports', '3000 5000', 'UDP')
        self.assertEqual(call.args[0], ['nordvpn', 'allowlist', 'add', 'ports', '3000', '5000', 'protocol', 'UDP'])
        call, _ = self.run_with('allowlist', 'remove', 'subnet', '192.168.1.42/24')
        self.assertEqual(call.args[0][-1], '192.168.1.0/24')
        for kind, value in [('ports', '5000 3000'), ('port', '0'), ('port', '65536'), ('ports', '22'), ('subnet', 'bad')]:
            with self.assertRaises(NordError):
                Client().allowlist('add', kind, value)

    def test_actual_subprocess_transport(self):
        # A local fake executable exercises the actual subprocess boundary.
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'nordvpn')
            with open(path, 'w') as stream:
                stream.write('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            os.chmod(path, 0o700)
            self.assertEqual(Client(path).connect('United States'), 'connect\nUnited_States')


if __name__ == '__main__':
    unittest.main()
