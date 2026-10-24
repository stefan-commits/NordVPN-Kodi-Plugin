"""Exercise remote-control workflows without requiring a Kodi installation."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch


class UITests(unittest.TestCase):
    def setUp(self):
        self.kodi = {name: MagicMock() for name in ('xbmc', 'xbmcgui', 'xbmcaddon')}
        self.modules = patch.dict(sys.modules, self.kodi)
        self.modules.start()
        spec = importlib.util.spec_from_file_location('nordvpn_ui_test', Path(__file__).resolve().parents[1] / 'addon.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.app = module.App()
        self.token_dir = tempfile.TemporaryDirectory()
        self.app.token_path = Path(self.token_dir.name) / "access_token.txt"
        self.app.monitor.abortRequested.return_value = False
        self.app.execute = MagicMock()
        self.app.command = MagicMock()

    def tearDown(self):
        self.modules.stop()
        self.token_dir.cleanup()

    def test_empty_file_does_not_run_command(self):
        from resources.lib.nordvpn import NordError
        with self.assertRaises(NordError):
            self.app.login()
        self.app.execute.assert_not_called()
        self.app.dialog.input.assert_not_called()

    def test_flatpak_setting_reloaded(self):
        self.app.addon.getSetting.side_effect = lambda key: {'cli_path': '/usr/bin/nordvpn', 'flatpak_host': 'true'}[key]
        self.app.configure()
        self.assertTrue(self.app.client.flatpak_host)
        self.assertEqual(self.app.client.executable, '/usr/bin/nordvpn')

    def test_login_reads_file_without_prompt_or_settings_storage(self):
        self.app.token_path.write_text('my-token\n')
        self.app.login()
        self.app.execute.assert_called_once_with(self.app.client.login, 'my-token')
        self.app.addon.setSetting.assert_not_called()
        self.app.dialog.input.assert_not_called()

    def test_cancel_country_does_not_connect(self):
        self.app.execute.return_value = ['Canada']
        self.app.dialog.select.return_value = -1
        self.app.location()
        self.assertEqual(self.app.execute.call_count, 1)

    def test_country_city_connect(self):
        self.app.execute.side_effect = [['Canada'], ['Toronto'], 'Connected']
        self.app.dialog.select.side_effect = [0, 1]
        self.app.location()
        self.assertEqual(self.app.execute.call_args.args, (self.app.client.connect, 'Canada', 'Toronto', ''))

    def test_cancel_logout_does_nothing(self):
        self.app.dialog.yesno.return_value = False
        self.app.logout()
        self.app.execute.assert_not_called()

    def test_logout_always_preserves_token(self):
        self.app.token_path.write_text('my-token')
        self.app.dialog.yesno.return_value = True
        self.app.logout()
        self.app.execute.assert_called_once_with(self.app.client.logout)
        self.app.dialog.select.assert_not_called()
        self.assertEqual(self.app.token_path.read_text(), 'my-token')

    def test_protocol_selection(self):
        self.app.dialog.select.side_effect = [1, 3, -1]
        self.app.settings()
        self.app.command.assert_called_once_with('set', 'protocol', 'nordwhisper')

    def test_exit_main_menu(self):
        self.app.dialog.select.return_value = -1
        with patch.object(sys, 'platform', 'linux'):
            self.app.run()
        self.app.command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
