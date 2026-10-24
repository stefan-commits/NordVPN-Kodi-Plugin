"""Package only the current CLI front end, excluding all legacy service code."""
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
metadata = ET.parse(root / 'addon.xml').getroot()
output = root / 'dist' / '{}-{}.zip'.format(metadata.attrib['id'], metadata.attrib['version'])
output.parent.mkdir(exist_ok=True)
files = ['addon.xml', 'addon.py', 'icon.png', 'LICENSE.txt', 'README.md',
         'resources/settings.xml', 'resources/lib/__init__.py', 'resources/lib/nordvpn.py',
         'resources/lib/tokenfile.py']
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
    for name in files:
        archive.write(root / name, metadata.attrib['id'] + '/' + name)
print(output)
