import os
from pathlib import Path
import tempfile
import unittest

from resources.lib.nordvpn import NordError
from resources.lib.tokenfile import ensure_token_file, read_token


class TokenFileTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / 'access_token.txt'

    def tearDown(self):
        self.folder.cleanup()

    def test_template_permissions_and_preservation(self):
        ensure_token_file(self.path)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)
        with self.assertRaises(NordError):
            read_token(self.path)
        self.path.write_text('secret-token')
        ensure_token_file(self.path)
        self.assertEqual(read_token(self.path), 'secret-token')

    def test_comments_bom_and_whitespace(self):
        self.path.write_text('\ufeff# comment\r\n\n secret-token \r\n', encoding='utf-8')
        self.assertEqual(read_token(self.path), 'secret-token')
        self.path.write_text('replacement-token')
        self.assertEqual(read_token(self.path), 'replacement-token')

    def test_invalid_input_never_exposed(self):
        for value in ('secret-token\nsecond-token', 'secret-token with spaces', '"secret-token"', '--secret-token', 'secret-token\x00', 'secret-token' * 1000):
            self.path.write_text(value)
            with self.assertRaises(NordError) as context:
                read_token(self.path)
            self.assertNotIn('secret-token', str(context.exception))

    def test_missing_and_invalid_encoding(self):
        with self.assertRaises(NordError):
            read_token(self.path)
        self.path.write_bytes(b'\xff')
        with self.assertRaises(NordError):
            read_token(self.path)
