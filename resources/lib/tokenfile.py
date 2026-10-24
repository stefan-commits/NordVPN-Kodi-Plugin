"""User-edited access token file; never include its contents in diagnostics."""
import os
from pathlib import Path

from resources.lib.nordvpn import NordError


TEMPLATE = '# Paste your NordVPN access token on the next line.\n# One token only; no quotes. Lines starting with # are ignored.\n'


def ensure_token_file(path):
    """Create an owner-only template once, preserving any existing contents."""
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    except OSError:
        raise NordError('Cannot create the token file. Create access_token.txt in the add-on directory and make it readable by the Kodi user.') from None
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(TEMPLATE)
    except OSError:
        raise NordError('Cannot write the token file template.') from None


def read_token(path):
    try:
        with Path(path).open(encoding='utf-8-sig') as stream:
            contents = stream.read(8193)
    except (OSError, UnicodeError):
        raise NordError('Cannot read access_token.txt. Check that it exists in the add-on directory and is readable by the Kodi user.') from None
    lines = [line.strip() for line in contents.splitlines()
             if line.strip() and not line.lstrip().startswith('#')]
    if not lines:
        raise NordError('The token file is empty. Edit access_token.txt in the add-on directory, paste your token on its own line, save, then select Log in from token file again.')
    if len(contents) > 8192 or len(lines) != 1 or any(c.isspace() for c in lines[0]) or lines[0].startswith('-') or any(c in lines[0] for c in '\"\'\x00'):
        raise NordError('Invalid token file format. Use one token on one line, without quotes or spaces. Comment lines may start with #.')
    return lines[0]
