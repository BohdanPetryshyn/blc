# blc

Block websites on a schedule on macOS, using only what ships with the system:
`/etc/resolver`, launchd, and the Python 3 from the Xcode Command Line Tools.

## Install

```bash
sudo ./install.sh
```

Re-run it after changing the code. It needs `/usr/bin/python3` (`xcode-select --install`).
macOS will show a "background item added" notice for `python3`; that's the blc daemon.

Then turn off **iCloud Private Relay** (System Settings → your name → iCloud → Private Relay),
or at least for your Wi-Fi network (Wi-Fi → Details → Limit IP address tracking / Private Relay).
With it on, Safari resolves names through Apple and never sees the block.

## Usage

```bash
blc block youtube.com 00:00 19:00     # youtube.com and every subdomain, midnight to 7pm
blc block reddit.com                  # all day
blc block x.com 22:00 07:00           # windows can wrap past midnight
blc pause youtube.com 30min "Need to watch the conference talk a client sent me for the proposal"
blc resume youtube.com                # end a pause early
blc unblock youtube.com "Done with this experiment, YouTube is only for music on this machine now"
blc status                            # or just: blc
blc log                               # history of blocks, pauses and unblocks with comments
```

- A domain always includes all of its subdomains. A leading `*.` is accepted and ignored.
- `block` adds a time window; running it again with another window adds a second one.
  Loosening a block means `unblock` and `block` again.
- `pause` (max 2h) and `unblock` need a comment of at least 50 characters, kept in `~/.config/blc/log`.

## How it works

`blc` edits `~/.config/blc/config.json`. A root LaunchDaemon (`local.blc`, running `blc daemon`)
re-reads it every 2 seconds and keeps one file per currently blocked domain in `/etc/resolver`:

```
# managed by blc
nameserver 127.0.0.1
port 54
```

macOS then sends lookups for that domain and its subdomains to `127.0.0.1:54`, where the daemon
answers "no such domain", so Safari fails at once with "can't find the server". If the daemon is
down, lookups still fail, just after a 30 second timeout. The daemon log is `/var/log/blc.log`.

## Limits

- It's an honor system: the config is a plain file in your home folder.
- Tabs that are already open can keep working for a few minutes over existing connections.
- VPNs and apps with their own DNS-over-HTTPS (Chrome "secure DNS", Firefox) can bypass it.
- `dig` and `nslookup` ignore `/etc/resolver`; check with `dscacheutil -q host -a name youtube.com`.

## Uninstall

```bash
sudo ./uninstall.sh
```

Lifts all blocks and removes the daemon; your rules and log stay in `~/.config/blc`.

## Tests

```bash
python3 -m unittest discover -s tests
```
