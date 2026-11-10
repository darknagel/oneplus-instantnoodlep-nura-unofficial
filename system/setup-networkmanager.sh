#!/bin/sh
# Run once as root on the Nura systemd image; safe to run again.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run as root.' >&2; exit 1; }
[ -x /usr/lib/systemd/system-generators/nm-initrd-generator.sh ]
[ -f /usr/lib/systemd/system/NetworkManager-dispatcher.service ]
# The generator is a Bash script. Keep the interpreter in the installed set.
apk add bash
# Install the service's D-Bus activation alias without restarting networking.
systemctl enable NetworkManager-dispatcher.service
