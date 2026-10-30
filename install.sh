#!/bin/zsh
# Install or update blc: copy it to /usr/local/bin and (re)start the root daemon.
# Usage: sudo ./install.sh
set -eu

LABEL=local.blc
PLIST=/Library/LaunchDaemons/$LABEL.plist
BIN=/usr/local/bin/blc

if [[ $EUID -ne 0 || -z ${SUDO_USER:-} ]]; then
  echo "run as: sudo ./install.sh" >&2
  exit 1
fi

src=${0:A:h}
home=$(dscl . -read /Users/$SUDO_USER NFSHomeDirectory | awk '{print $2}')
config=$home/.config/blc/config.json

if ! /usr/bin/python3 -I -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
  echo "blc needs Python 3.9+ at /usr/bin/python3: run xcode-select --install" >&2
  exit 1
fi

# Copy rather than symlink: the daemon runs this file as root, so it must not stay user-writable.
mkdir -p /usr/local/bin
install -m 755 -o root -g wheel $src/blc $BIN
sed "s#__CONFIG__#$config#" $src/launchd/$LABEL.plist > $PLIST
chown root:wheel $PLIST
chmod 644 $PLIST

if launchctl print system/$LABEL >/dev/null 2>&1; then
  launchctl bootout system/$LABEL
  sleep 1
fi
launchctl bootstrap system $PLIST

echo "blc installed. Config: $config, daemon log: /var/log/blc.log"
echo "Turn off iCloud Private Relay (at least for your Wi-Fi), or Safari will skip the block."
