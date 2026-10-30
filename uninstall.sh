#!/bin/zsh
# Stop the daemon, lift every block and remove blc. Keeps ~/.config/blc.
# Usage: sudo ./uninstall.sh
set -eu

LABEL=local.blc

if [[ $EUID -ne 0 ]]; then
  echo "run as: sudo ./uninstall.sh" >&2
  exit 1
fi

launchctl bootout system/$LABEL 2>/dev/null || true
rm -f /Library/LaunchDaemons/$LABEL.plist /usr/local/bin/blc

for file in /etc/resolver/*(N); do
  if [[ $(head -n 1 $file) == "# managed by blc" ]]; then
    rm -f $file
  fi
done
rmdir /etc/resolver 2>/dev/null || true

dscacheutil -flushcache
killall -HUP mDNSResponder
echo "blc removed. Your rules and log are still in ~/.config/blc."
