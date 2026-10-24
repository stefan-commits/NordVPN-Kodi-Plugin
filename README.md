# NordVPN CLI for Kodi

An unofficial Kodi program add-on using Python's standard library to execute the
installed NordVPN Linux CLI. No Python packages, browser in Kodi, OpenVPN profile
downloads, shell commands, or separate VPN connection manager are required.

## Requirements and installation

- Kodi 19 or newer with Python 3 on Linux.
- NordVPN Linux CLI and daemon installed and working on the same device.
- The account running Kodi must have permission to use NordVPN (normally membership
  in the `nordvpn` group). Restart the user's session/device after changing groups.
- A NordVPN subscription and an access token generated in Nord Account on another
  device. Installing the Linux service and generating a token are one-time setup
  prerequisites; this add-on cannot install system packages or generate tokens.

Install `dist/service.nord.vpn-6.0.4.zip` using Kodi's **Add-ons → Install from zip
file** (enable Unknown sources if required). Open **Program add-ons → NordVPN CLI**,
edit the token file described below, choose **Log in from token file**, then
**Quick connect** or choose a location.
Use **Status** to check the actual daemon state. If Kodi cannot find `nordvpn`, set
its full executable path, usually `/usr/bin/nordvpn`, in Add-on settings.

This needs an OS capable of running the official NordVPN Linux client. Android,
Windows, macOS and stock appliance images without that client are not supported.
Flatpak Kodi requires the host-command setup below to reach the host executable and daemon.
The add-on does not run sudo or ask for a system password.

## Flatpak Kodi on Debian

Inside Flatpak, `/usr/bin` belongs to the runtime, not Debian. Setting the executable
path alone cannot reach Debian's NordVPN client. Version 6.0.1 adds an explicit
**Flatpak host commands** setting that uses `flatpak-spawn --host` without a shell.

For the Flathub Kodi app (`tv.kodi.Kodi`), close Kodi and run on Debian as your
normal user (no sudo):

```sh
flatpak override --user --talk-name=org.freedesktop.Flatpak tv.kodi.Kodi
flatpak run --command=flatpak-spawn tv.kodi.Kodi --host /usr/bin/nordvpn version
```

The second command should print the NordVPN version. This permission allows Kodi
and its add-ons to execute host commands as your user; it is broader than access
to NordVPN alone. A native Debian Kodi installation is an alternative that avoids
this Flatpak override. The add-on does not change Flatpak permissions itself.

Install the updated ZIP, set the executable to `/usr/bin/nordvpn`, enable
**Flatpak host commands**, and try **More controls / CLI help → NordVPN version**,
then **Status**. Do not put `flatpak-spawn --host` into the executable field.
If your Kodi application ID differs, use the ID shown by `flatpak list --app`.
To explicitly deny the added host-command permission later:

```sh
flatpak override --user --no-talk-name=org.freedesktop.Flatpak tv.kodi.Kodi
```

Host launch failures and permission errors appear in Kodi. A timeout ends the
launcher, but a host CLI or daemon operation may continue; check Status before
retrying. Flatpak transport is covered by mocked tests; validate on the real device.

## Controls

- Login from a user-edited token file; account information; logout that always preserves the token.
- Quick connect; live country/city and group lists; specific server name; disconnect.
- Live status and settings shown directly from NordVPN.
- Protocol: NordLynx, OpenVPN UDP/TCP, NordWhisper.
- Auto-connect with optional country/city/group, DNS, Kill Switch, protection,
  notifications, post-quantum VPN, ECH, and Meshnet toggles.
- Add/remove allowlisted ports, ranges and subnets, and clear the allowlist.
- Meshnet peer listing/routing, connection rating, CLI version and help.
- **More controls → Set another option** shows installed help for a setting and
  accepts space-separated values, allowing additional simple settings without an
  add-on update. It accepts identifiers, not arbitrary shell syntax.

Auto-connect is owned by NordVPN, so it also works while Kodi is closed. Changes
are sent directly to the daemon; Kodi does not maintain a duplicate VPN settings
store. The CLI reports incompatible settings (for example post-quantum/OpenVPN,
post-quantum/Meshnet, and DNS/protection). ECH requires NordWhisper and reconnecting
for changes to take effect. Available features depend on the installed CLI.

The command mappings target the supplied NordVPN 6.0.1 manual. Older versions with
`set technology` and `set protocol udp/tcp` can use the additional setting control;
the main protocol picker targets the supplied manual's unified protocol names.
Meshnet invitations, peer permission editing and file transfers are not implemented
as dedicated workflows. This release covers VPN control rather than every CLI
subcommand. No automatic per-Kodi-add-on routing is enabled.

## Token handling

On first launch, the add-on creates `access_token.txt` beside `addon.py` with
owner-only permissions. Select **Token file location** in Kodi to see its exact
path. Edit the file using your preferred text editor, paste the token on one line
without quotes, and save. Blank lines and lines starting with `#` are ignored.
Choose **Log in from token file**; there is no token-entry dialog. Each login reads
the file again, so changes do not require restarting Kodi.

For your Flatpak installation, the usual host path is:

```text
/home/stef/.var/app/tv.kodi.Kodi/data/kodi/addons/service.nord.vpn/access_token.txt
```

Kodi's displayed path may use its internal Flatpak view. For native Kodi the usual
location is `~/.kodi/addons/service.nord.vpn/access_token.txt`.

The token is stored as plain text in this file as requested. Keep the file readable
only by your account (`chmod 600 access_token.txt` after editing if needed). The
add-on never displays its contents or puts the token in Kodi settings, plugin URLs,
or logs. It redacts the token from CLI responses. The CLI requires the token in
process arguments during login; privileged local process inspection can see it.

Existing files are never overwritten by the add-on. The ZIP builder excludes the
actual token file, so a locally entered token cannot be distributed in a release.
Kodi may replace the add-on directory when updating or reinstalling: keep a secure
copy of your token and restore it if needed after an upgrade.

Logout always preserves the token and leaves its file intact. Kodi has no token
revocation option. The add-on checks `logout --help` before logging out, using
`--revoke-token=false` on modern clients or `--persist-token` on older clients.
If neither option is advertised, logout stops without changing the session.
It never falls back to a potentially revoking logout command.

To intentionally revoke a token, use the NordVPN CLI manually outside Kodi. For
NordVPN 6.0.1, the command is `nordvpn logout --revoke-token`. After revocation,
replace the token in the file before logging in again. NordVPN keeps its own
session, so editing the file alone does not change the current login.

Current logout implementation:
https://github.com/NordSecurity/nordvpn-linux/blob/main/cli/cli_logout.go

Token generation instructions (logout examples describe older CLI versions):
https://support.nordvpn.com/hc/en-us/articles/20286980309265-How-to-log-in-to-NordVPN-without-a-GUI-using-a-token

## Errors and troubleshooting

Commands run off the UI thread, with closed standard input and a 90-second timeout.
Errors appear in Kodi. A timeout can leave a daemon operation in progress; check
Status before retrying. Missing executable, daemon/socket permissions, invalid
credentials and incompatible options are reported rather than treated as success.
Use CLI help for the installed version if a documented command is rejected.

If enabling Kill Switch blocks connectivity while disconnected, connect again or
disable it in NordVPN settings. Allowlisting exposes the selected ports/subnets
outside VPN protection; add only the entries you need.

## Development and validation

Run from this directory:

```sh
python3 -m unittest discover -s tests -v
python3 tools/build_zip.py
```

Tests cover command arguments, real subprocess transport against a fake executable,
validation, token redaction, timeouts, and Kodi workflows with mocked dialogs.
They do not prove a real VPN connection or Kodi skin compatibility. On the target
Linux device, verify token login, status, quick connect, country/city/group/server
selection, disconnect, settings readback, and token-preserving logout. Check that remote
Back cancels selections and that errors render correctly. Confirm the same token can be used to log in again after logout.

The previous entry point, manifest, settings and README are preserved in
`legacy-backup/original-addon.tar.gz`. Other original source files remain available
for reference. The new manifest does not register the old background service, and
the ZIP builder explicitly excludes legacy code. Restart Kodi after upgrading an
already installed legacy version so its old service stops. The original GPL license
is retained; this project is not an official NordVPN product.
